"""Running the classifier against one document, and turning every outcome into a state.

The seam between `evidence/processing.py` — which knows about documents, runs and the
states a user sees — and `ai/service.py`, which knows about providers, budgets and the
ledger. Neither should have to learn the other's vocabulary, and this module is where
the translation is written down once.

**Every path here ends in a state, not an exception.** `classify` returns an outcome
for a provider failure, a refused budget, an exhausted deadline and a successful
abstention alike. That is directive 7 as a signature: a pipeline that could receive an
exception it forgot to catch would leave a document sitting in `ANALYSING` with nothing
left to move it, which is the false-reassurance failure — the UI says "analysing", the
truth is "nothing will ever happen", and only a log knows.

**The user's category is never overwritten.** `EvidenceItem.category` is what the
person chose at upload. This module writes only to `ExtractionRun`. There is no
assignment to `item.category` anywhere in it, and `tests/ai/test_classification.py`
asserts that by mutation.
"""

import uuid
from dataclasses import dataclass

import structlog
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.classifier import MAX_INPUT_CHARACTERS, ClassificationOutput, ClassifiedCategory
from app.ai.domain import Capability, utcnow
from app.ai.extraction_run import SUMMARY_FOR_STATUS, ExtractionRun, ExtractionRunStatus
from app.ai.provider import AIProvider, DocumentText
from app.ai.repository import ExtractionRunRepository
from app.ai.service import AiBudget, AiDeadlineExceeded, invoke
from app.ai.spend import SpendCeilingReached
from app.core.config import Settings

_log = structlog.get_logger()


@dataclass(frozen=True)
class ClassificationOutcome:
    """What the pipeline needs to know, with nothing the model said that it should not
    act on. `category` is `None` whenever no answer was produced, so a caller cannot
    read a failure as a classification."""

    run: ExtractionRun
    category: ClassifiedCategory | None
    #: Why a document ended up where it did, in language a user can act on. Not an
    #: exception string: a provider error can quote the request, and the request is the
    #: document.
    user_summary: str | None = None

    @property
    def produced_an_answer(self) -> bool:
        return self.category is not None


def _truncate(text: str) -> str:
    """What the model actually sees.

    A classifier is decided by letterheads, titles and reference numbers, which are on
    the first page. Sending all 200,000 characters `extraction.py` permits would cost
    roughly forty times the M8 spike's per-document figure to reach the same answer.
    """
    return text[:MAX_INPUT_CHARACTERS]


def classify(
    provider: AIProvider,
    session: Session,
    *,
    case_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    processing_run_id: uuid.UUID,
    document_text: str,
    budget: AiBudget,
    settings: Settings,
    trace_id: str | None = None,
) -> ClassificationOutcome:
    """Classify one document. Returns an outcome for every path; raises for none."""
    sent = _truncate(document_text)
    # Captured before anything is attempted, so the run's own timestamps bracket the work
    # rather than being read off the transaction that records it.
    started_at = utcnow()

    def _run(
        status: ExtractionRunStatus,
        *,
        model_run_id: uuid.UUID | None = None,
        output: ClassificationOutput | None = None,
    ) -> ExtractionRun:
        return ExtractionRun.record(
            case_id=case_id,
            evidence_item_id=evidence_item_id,
            evidence_file_id=evidence_file_id,
            processing_run_id=processing_run_id,
            capability=Capability.DOCUMENT_CLASSIFIER.value,
            status=status,
            input_text=sent,
            started_at=started_at,
            model_run_id=model_run_id,
            classified_category=output.category.value if output else None,
            classification_confidence=output.confidence if output else None,
            classification_reasoning=output.reasoning if output else None,
        )

    used = ExtractionRunRepository.calls_today(session, case_id=case_id, at=started_at)
    if used >= settings.ai_case_daily_call_limit:
        # Checked before the deadline and the ceiling, because it is the cheapest of the
        # three and the only one whose cause is this case's own behaviour. Told apart
        # from the deployment ceiling deliberately: "you have had your share" and "nobody
        # gets any more" are different sentences, and giving a user the second when the
        # first is true blames the system for their own loop.
        _log.warning(
            "ai.classification_refused_quota",
            evidence_item_id=str(evidence_item_id),
            calls_today=used,
            limit=settings.ai_case_daily_call_limit,
        )
        return ClassificationOutcome(
            run=_run(ExtractionRunStatus.REFUSED_QUOTA),
            category=None,
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_QUOTA],
        )

    owned = ExtractionRunRepository.calls_today_for_the_owner_of(
        session, case_id=case_id, at=started_at
    )
    if owned >= settings.ai_user_daily_call_limit:
        # After the case check, so the narrower message wins when both apply: being told
        # "this case has had its share" is more actionable than "you have", when only one
        # of your cases is affected.
        _log.warning(
            "ai.classification_refused_user_quota",
            evidence_item_id=str(evidence_item_id),
            calls_today=owned,
            limit=settings.ai_user_daily_call_limit,
        )
        return ClassificationOutcome(
            run=_run(ExtractionRunStatus.REFUSED_USER_QUOTA),
            category=None,
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_USER_QUOTA],
        )

    try:
        result = invoke(
            provider,
            capability=Capability.DOCUMENT_CLASSIFIER,
            document=DocumentText(sent),
            output_schema=ClassificationOutput,
            budget=budget,
            trace_id=trace_id,
            settings=settings,
        )
    except SpendCeilingReached:
        # A working system refusing to spend more today, not a broken one. The message
        # says what happened and when it clears, because "processing failed" would send
        # someone to re-upload a document that is perfectly fine.
        _log.warning("ai.classification_refused_no_budget", evidence_item_id=str(evidence_item_id))
        return ClassificationOutcome(
            run=_run(ExtractionRunStatus.REFUSED_NO_BUDGET),
            category=None,
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_NO_BUDGET],
        )
    except AiDeadlineExceeded:
        _log.warning("ai.classification_refused_no_time", evidence_item_id=str(evidence_item_id))
        return ClassificationOutcome(
            run=_run(ExtractionRunStatus.REFUSED_NO_TIME),
            category=None,
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_NO_TIME],
        )

    if not result.succeeded or result.parsed is None:
        # Includes a refusal, an exhausted retry cap, a timeout, and output that never
        # validated. All of them mean the same thing to a user — we read it, we did not
        # work out what it is — and none of them may invent a category.
        _log.warning(
            "ai.classification_failed",
            evidence_item_id=str(evidence_item_id),
            status=result.status.value,
            attempts=result.attempts,
        )
        return ClassificationOutcome(
            run=_run(ExtractionRunStatus.FAILED, model_run_id=result.model_run_id),
            category=None,
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.FAILED],
        )

    output = result.parsed
    abstained = output.category in (ClassifiedCategory.UNSUPPORTED, ClassifiedCategory.AMBIGUOUS)
    status = ExtractionRunStatus.ABSTAINED if abstained else ExtractionRunStatus.SUCCEEDED

    _log.info(
        "ai.classified",
        evidence_item_id=str(evidence_item_id),
        # The category and the confidence, never the reasoning: that is the one field
        # whose contents the *document* influences, and a log aggregator is exactly
        # where a fragment of someone's document should not end up.
        category=output.category.value,
        confidence=round(output.confidence, 3),
        model_run_id=str(result.model_run_id),
        trace_id=trace_id,
    )
    return ClassificationOutcome(
        run=_run(status, model_run_id=result.model_run_id, output=output),
        category=output.category,
    )


def validate_output(payload: dict[str, object]) -> ClassificationOutput | None:
    """Parse a payload the way the capability would, returning None rather than raising.

    Used by the eval harness, which needs to distinguish "the model returned something
    the schema rejects" from "the harness crashed" — and treat only the first as a
    measurement (AI_SPIKE_FINDINGS §5: an instrument that reads success off a failed
    call is the false-reassurance failure in miniature).
    """
    try:
        return ClassificationOutput.model_validate(payload)
    except ValidationError:
        return None
