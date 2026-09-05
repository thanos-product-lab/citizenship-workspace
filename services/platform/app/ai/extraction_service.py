"""Running the travel extractor, and turning what it returns into claims.

The same shape as `classification_service`: every outcome is a state, nothing raises at
the pipeline. What is new is the last step — this is the first code in the product that
creates an `ExtractedClaim`, and therefore the first that puts a model's output in front
of a person as something they could confirm.

**It creates claims and nothing else.** No `FactVersion`, no `CaseFact`, no
`FactEvidenceLink`. Those need a `ReviewedValue`, and only a flushed
`ClaimReviewDecision` produces one — so there is no argument this module could pass to
make a fact, and `tests/facts/test_boundary.py` asserts it cannot even name the types.

**A null field creates no claim.** A journey with no return date yields no
`travel.return_date` claim at all, rather than a claim whose value is empty. The
distinction matters: an absent claim is "the document did not say", and a claim with a
blank value is a proposal to confirm nothing, which a review queue would ask someone to
decide about.
"""

import uuid
from dataclasses import dataclass, field

import structlog
from sqlalchemy.orm import Session

from app.ai.domain import Capability, utcnow
from app.ai.extraction_run import SUMMARY_FOR_STATUS, ExtractionRun, ExtractionRunStatus
from app.ai.extractors import (
    MAX_INPUT_CHARACTERS,
    TRAVEL_FIELDS,
    ExtractedDate,
    Journey,
    TravelExtraction,
)
from app.ai.provider import AIProvider, DocumentText
from app.ai.repository import ExtractionRunRepository
from app.ai.service import AiBudget, AiDeadlineExceeded, invoke
from app.ai.spend import SpendCeilingReached
from app.core.config import Settings
from app.facts.domain import SCHEMA_FOR_CLAIM_TYPE, ExtractedClaim
from app.facts.values import ProposedValue, ValueSchema

_log = structlog.get_logger()


@dataclass(frozen=True)
class ExtractionOutcome:
    """What an extraction produced: a run, and the claims it proposed.

    `claims` is empty for every refusal and every failure, and empty is also a valid
    *success* — a travel document with no readable journey proposes nothing. The run's
    status is what tells those apart, which is why the caller reads it rather than
    counting claims.
    """

    run: ExtractionRun
    claims: list[ExtractedClaim] = field(default_factory=list)
    user_summary: str | None = None

    @property
    def proposed_anything(self) -> bool:
        return bool(self.claims)


def extract_travel(
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
) -> ExtractionOutcome:
    """Extract journeys from one travel document. Returns for every path; raises for none."""
    sent = document_text[:MAX_INPUT_CHARACTERS]
    started_at = utcnow()

    def _run(
        status: ExtractionRunStatus, *, model_run_id: uuid.UUID | None = None
    ) -> ExtractionRun:
        return ExtractionRun.record(
            case_id=case_id,
            evidence_item_id=evidence_item_id,
            evidence_file_id=evidence_file_id,
            processing_run_id=processing_run_id,
            capability=Capability.TRAVEL_RECORD_EXTRACTOR.value,
            status=status,
            input_text=sent,
            started_at=started_at,
            model_run_id=model_run_id,
        )

    # The same three refusals the classifier has, in the same order and for the same
    # reasons. Duplicated rather than shared: a helper spanning both capabilities would
    # be the shared-prompt mistake in another register — one capability's change quietly
    # altering another's behaviour (AI_SPIKE_FINDINGS §3.2).
    used = ExtractionRunRepository.calls_today(session, case_id=case_id, at=started_at)
    if used >= settings.ai_case_daily_call_limit:
        return _refused(_run(ExtractionRunStatus.REFUSED_QUOTA), ExtractionRunStatus.REFUSED_QUOTA)
    owned = ExtractionRunRepository.calls_today_for_the_owner_of(
        session, case_id=case_id, at=started_at
    )
    if owned >= settings.ai_user_daily_call_limit:
        return _refused(
            _run(ExtractionRunStatus.REFUSED_USER_QUOTA), ExtractionRunStatus.REFUSED_USER_QUOTA
        )

    try:
        result = invoke(
            provider,
            capability=Capability.TRAVEL_RECORD_EXTRACTOR,
            document=DocumentText(sent),
            output_schema=TravelExtraction,
            budget=budget,
            trace_id=trace_id,
            settings=settings,
        )
    except SpendCeilingReached:
        return _refused(
            _run(ExtractionRunStatus.REFUSED_NO_BUDGET), ExtractionRunStatus.REFUSED_NO_BUDGET
        )
    except AiDeadlineExceeded:
        return _refused(
            _run(ExtractionRunStatus.REFUSED_NO_TIME), ExtractionRunStatus.REFUSED_NO_TIME
        )

    if not result.succeeded or result.parsed is None:
        _log.warning(
            "ai.travel_extraction_failed",
            evidence_item_id=str(evidence_item_id),
            status=result.status.value,
            attempts=result.attempts,
        )
        return ExtractionOutcome(
            run=_run(ExtractionRunStatus.FAILED, model_run_id=result.model_run_id),
            user_summary=SUMMARY_FOR_STATUS[ExtractionRunStatus.FAILED],
        )

    run = _run(ExtractionRunStatus.SUCCEEDED, model_run_id=result.model_run_id)
    session.add(run)
    # Flushed so the claims can reference it: a claim names the run that proposed it, and
    # `extraction_run_id` is half of the unique key that stops a redelivery duplicating a
    # user's review queue.
    session.flush()

    claims = _claims_from(
        result.parsed,
        case_id=case_id,
        evidence_item_id=evidence_item_id,
        evidence_file_id=evidence_file_id,
        run_id=run.id,
        confidence=None,
    )
    for claim in claims:
        session.add(claim)

    _log.info(
        "ai.travel_extracted",
        evidence_item_id=str(evidence_item_id),
        # Counts and types. Never a value — a claim's value is a fragment of someone's
        # document, and this is a log.
        journeys=len(result.parsed.journeys),
        claims=len(claims),
        claim_types=sorted({c.claim_type for c in claims}),
        model_run_id=str(result.model_run_id),
        trace_id=trace_id,
    )
    return ExtractionOutcome(run=run, claims=claims)


def _refused(run: ExtractionRun, status: ExtractionRunStatus) -> ExtractionOutcome:
    return ExtractionOutcome(run=run, user_summary=SUMMARY_FOR_STATUS[status])


def _claims_from(
    extraction: TravelExtraction,
    *,
    case_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    run_id: uuid.UUID,
    confidence: float | None,
) -> list[ExtractedClaim]:
    """One claim per field the document actually stated.

    `journey_index` distinguishes the same field across journeys (RFC §41.2) — without
    it a two-journey booking would propose two `travel.departure_date` claims that
    nothing could tell apart, and the unique key would reject the second.
    """
    claims: list[ExtractedClaim] = []
    for index, journey in enumerate(extraction.journeys):
        for field_name, claim_type in TRAVEL_FIELDS.items():
            raw = getattr(journey, field_name)
            value = _value_for(raw, schema=SCHEMA_FOR_CLAIM_TYPE[claim_type])
            if value is None:
                # The document did not say. No claim, rather than a claim proposing
                # nothing — a review queue must not ask someone to decide about a blank.
                continue
            claims.append(
                ExtractedClaim.propose(
                    case_id=case_id,
                    evidence_item_id=evidence_item_id,
                    evidence_file_id=evidence_file_id,
                    extraction_run_id=run_id,
                    claim_type=claim_type,
                    value=value,
                    journey_index=index,
                    model_confidence=confidence,
                )
            )
    return claims


def _value_for(raw: object, *, schema: ValueSchema) -> ProposedValue | None:
    if schema is ValueSchema.DATE_V1:
        if not isinstance(raw, ExtractedDate) or not raw.as_written:
            return None
        return ProposedValue(schema=schema, raw=raw.as_written, model_iso=raw.iso)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return ProposedValue(schema=schema, raw=raw)


def journeys_of(extraction: TravelExtraction) -> list[Journey]:
    """Exposed for the eval harness, which grades journeys rather than claims."""
    return list(extraction.journeys)
