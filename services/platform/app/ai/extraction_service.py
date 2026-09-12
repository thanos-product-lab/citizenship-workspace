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
from typing import Protocol

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.domain import Capability, utcnow
from app.ai.extraction_run import SUMMARY_FOR_STATUS, ExtractionRun, ExtractionRunStatus
from app.ai.extractors import (
    ENGLISH_FIELDS,
    LIFE_IN_UK_FIELDS,
    MAX_INPUT_CHARACTERS,
    TRAVEL_FIELDS,
    EnglishLanguageExtraction,
    ExtractedDate,
    Journey,
    LifeInUkExtraction,
    TravelExtraction,
)
from app.ai.provider import AIProvider, DocumentText
from app.ai.repository import ExtractionRunRepository
from app.ai.service import AiBudget, AiDeadlineExceeded, invoke
from app.ai.spend import SpendCeilingReached
from app.core.config import Settings
from app.facts.domain import SCHEMA_FOR_CLAIM_TYPE, ClaimType, ExtractedClaim
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


class DocumentExtractor(Protocol):
    """The shape the dispatch in `evidence.processing` selects by category.

    A Protocol rather than `Callable[..., ExtractionOutcome]`, which would accept any
    argument list and make a misspelled keyword at the one call site a runtime failure
    inside a Celery task. `extract_travel` satisfies this too, which is the point: the
    dispatch holds one type and the categories differ only in which function fills it.
    """

    def __call__(
        self,
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
        trace_id: str | None = ...,
    ) -> ExtractionOutcome: ...


def extract_english_language(
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
    """Extract the result from one English-language certificate.

    Spelled out rather than `**kwargs` forwarded: this signature is what `DocumentExtractor`
    checks against, and a `**kwargs: Any` wrapper would type-check while accepting a
    misspelled keyword the dispatch then fails on at run time.
    """
    return _extract_flat(
        provider,
        session,
        capability=Capability.ENGLISH_LANGUAGE_EXTRACTOR,
        output_schema=EnglishLanguageExtraction,
        fields=ENGLISH_FIELDS,
        case_id=case_id,
        evidence_item_id=evidence_item_id,
        evidence_file_id=evidence_file_id,
        processing_run_id=processing_run_id,
        document_text=document_text,
        budget=budget,
        settings=settings,
        trace_id=trace_id,
    )


def extract_life_in_uk(
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
    """Extract the result from one Life in the UK notification."""
    return _extract_flat(
        provider,
        session,
        capability=Capability.LIFE_IN_UK_EXTRACTOR,
        output_schema=LifeInUkExtraction,
        fields=LIFE_IN_UK_FIELDS,
        case_id=case_id,
        evidence_item_id=evidence_item_id,
        evidence_file_id=evidence_file_id,
        processing_run_id=processing_run_id,
        document_text=document_text,
        budget=budget,
        settings=settings,
        trace_id=trace_id,
    )


def _extract_flat[T: BaseModel](
    provider: AIProvider,
    session: Session,
    *,
    capability: Capability,
    output_schema: type[T],
    fields: dict[str, ClaimType],
    case_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    processing_run_id: uuid.UUID,
    document_text: str,
    budget: AiBudget,
    settings: Settings,
    trace_id: str | None = None,
) -> ExtractionOutcome:
    """One document, one flat set of fields. Returns for every path; raises for none.

    **Shared between the two test-result extractors, and deliberately not with
    `extract_travel`.** The note above `extract_travel`'s quota checks explains why that
    body is duplicated rather than shared with the classifier: a helper spanning two
    capabilities lets one capability's change quietly alter another's behaviour
    (AI_SPIKE_FINDINGS §3.2). The same reasoning gives the opposite answer here. These two
    are *one operation over two configurations* — read a flat document, map its fields to
    claim types — differing only in schema and field map, both passed in. Travel's is a
    different operation: its claims are journey-scoped, and a booking describing two
    journeys proposes the same claim type twice.

    So the line is drawn at the shape of the work rather than at the count of capabilities.
    Adding an immigration-status extractor should reuse this; adding a second travel-shaped
    one should not.
    """
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
            capability=capability.value,
            status=status,
            input_text=sent,
            started_at=started_at,
            model_run_id=model_run_id,
        )

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
            capability=capability,
            document=DocumentText(sent),
            output_schema=output_schema,
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
            "ai.extraction_failed",
            capability=capability.value,
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
    session.flush()

    claims = _claims_from_fields(
        result.parsed,
        fields=fields,
        case_id=case_id,
        evidence_item_id=evidence_item_id,
        evidence_file_id=evidence_file_id,
        run_id=run.id,
        confidence=None,
    )
    for claim in claims:
        session.add(claim)

    _log.info(
        "ai.extracted",
        capability=capability.value,
        evidence_item_id=str(evidence_item_id),
        # Counts and types. Never a value — a claim's value is a fragment of someone's
        # document, and this is a log.
        claims=len(claims),
        claim_types=sorted({c.claim_type for c in claims}),
        model_run_id=str(result.model_run_id),
        trace_id=trace_id,
    )
    return ExtractionOutcome(run=run, claims=claims)


def _claims_from_fields(
    extraction: BaseModel,
    *,
    fields: dict[str, ClaimType],
    case_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
    evidence_file_id: uuid.UUID,
    run_id: uuid.UUID,
    confidence: float | None,
) -> list[ExtractedClaim]:
    """One claim per field the document actually stated.

    No `journey_index`: these documents describe one thing. `facts.service.scope_key_for`
    already returns `""` for any claim type outside `JOURNEY_SCOPED_CLAIM_TYPES`, which
    makes the resulting fact case-level — one English test result per case, versioned if a
    second document proposes another.

    `_value_for` and `SCHEMA_FOR_CLAIM_TYPE` are reused untouched, so the rule that a date
    claim carries `as_written` and an advisory `iso` holds here by construction rather
    than by being restated.
    """
    claims: list[ExtractedClaim] = []
    for field_name, claim_type in fields.items():
        raw = getattr(extraction, field_name)
        value = _value_for(raw, schema=SCHEMA_FOR_CLAIM_TYPE[claim_type])
        if value is None:
            # The document did not say. No claim, rather than a claim proposing nothing —
            # a review queue must not ask someone to decide about a blank.
            continue
        claims.append(
            ExtractedClaim.propose(
                case_id=case_id,
                evidence_item_id=evidence_item_id,
                evidence_file_id=evidence_file_id,
                extraction_run_id=run_id,
                claim_type=claim_type,
                value=value,
                model_confidence=confidence,
            )
        )
    return claims


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
