"""Reviewing a claim: the one command that turns a proposal into a fact.

Everything the milestone is about happens in `review`. A user decides, a
`ClaimReviewDecision` is written and flushed, the decision produces a `ReviewedValue`,
and only then can a `FactVersion` exist. Each arrow is a type the previous step
produces and the next step requires; none of them is a check this function performs.

## Blind entry

RFC §41.4. For a high-risk (date) claim the caller does **not** send a decision. It
sends what the user typed, and this function works out which decision that was:

    entry matches the proposal  → CONFIRM,  review_mode = BLIND_ENTRY
    entry differs               → CORRECT,  review_mode = BLIND_ENTRY, value = the entry

The user's value always wins. That is the whole design: a split view with a value and
two buttons makes Confirm the path of least resistance, and a system recording
`USER_CONFIRMED_AI_CLAIM` cannot then tell "I checked" from "I clicked". Removing the
button removes the choice that was never really being made.

**The request schema for a high-risk claim carries no proposal**, so a client cannot
submit a confirmation it did not derive from something a person typed. See
`schemas.py`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase
from app.facts.domain import (
    HIGH_RISK_CLAIM_TYPES,
    OPEN_STATUSES,
    SCHEMA_FOR_CLAIM_TYPE,
    CaseFact,
    ClaimReviewDecision,
    ClaimStatus,
    ClaimType,
    ExtractedClaim,
    FactEvidenceLink,
    FactVersion,
    LinkAvailability,
    RejectionReason,
    ReviewDecision,
    ReviewMode,
    SupportType,
)
from app.facts.repository import ClaimRepository, FactRepository
from app.facts.values import ProposedValue, ValueSchema, normalise, parse_entered_date
from app.shared.errors import (
    ClaimAlreadyReviewed,
    ClaimNotFound,
    UnreadableEnteredValue,
)
from app.shared.unit_of_work import UnitOfWork

_log = structlog.get_logger()


@dataclass(frozen=True)
class ReviewOutcome:
    """What a review produced. `fact_version` is None for a rejection, because a
    rejection creates no trusted fact (RFC §10) — not "creates an empty one"."""

    claim: ExtractedClaim
    decision: ClaimReviewDecision
    fact_version: FactVersion | None


def review(
    session: Session,
    *,
    case: ApplicationCase,
    claim_id: uuid.UUID,
    user_id: str,
    entered_value: str | None = None,
    decision: ReviewDecision | None = None,
    reason_code: RejectionReason | None = None,
    expected_revision: int | None = None,
) -> ReviewOutcome:
    """Record a decision about one claim, and create the fact it authorises.

    `entered_value` is what the person typed. For a high-risk claim it is required and
    the decision is *derived* from it; for the rest the caller states the decision and
    `entered_value` carries a correction when there is one.
    """
    claim = ClaimRepository.get_for_case(session, case_id=case.id, claim_id=claim_id)
    if claim is None:
        raise ClaimNotFound()
    if ClaimStatus(claim.status) not in OPEN_STATUSES:
        # Deciding twice would either create a second fact from one proposal or
        # resurrect something already rejected. RFC §25: concurrency must not silently
        # overwrite review state.
        raise ClaimAlreadyReviewed(status=claim.status)

    claim_type = ClaimType(claim.claim_type)
    schema = SCHEMA_FOR_CLAIM_TYPE[claim_type]
    blind = claim_type in HIGH_RISK_CLAIM_TYPES

    resolved, mode, corrected_raw = _resolve(
        blind=blind,
        schema=schema,
        proposal=claim.proposed_value,
        entered_value=entered_value,
        stated=decision,
    )

    at = datetime.now(UTC)
    record = ClaimReviewDecision(
        case_id=case.id,
        claim_id=claim.id,
        decision=resolved.value,
        review_mode=mode.value,
        corrected_raw=corrected_raw,
        corrected_normalised=(
            normalise(ProposedValue(schema=schema, raw=corrected_raw))
            if corrected_raw is not None
            else None
        ),
        reason_code=reason_code.value if reason_code else None,
        reviewed_by=user_id,
        reviewed_at=at,
        claim_revision=expected_revision or 0,
    )
    session.add(record)
    # Flushed here, and this line is the boundary. `outcome()` needs `record.id`, which
    # only exists after the insert — so the decision is durable *before* anything can
    # produce the value a fact is built from.
    session.flush()

    uow = UnitOfWork(session, actor_id=user_id)

    if resolved is ReviewDecision.REJECT:
        claim.status = ClaimStatus.REJECTED.value
        _emit(uow, case, claim, record, fact_version=None)
        uow.commit()
        return ReviewOutcome(claim=claim, decision=record, fact_version=None)

    # The only call to `from_review` in the codebase, and it takes what `outcome()`
    # returns. Handing it the claim, or the claim's `proposed_value`, is a type error.
    reviewed = record.outcome(schema=schema)
    _fact, version = FactRepository.append_version(
        session, case_id=case.id, fact_type=claim.claim_type, reviewed=reviewed
    )

    session.add(
        FactEvidenceLink(
            case_id=case.id,
            fact_version_id=version.id,
            evidence_item_id=claim.evidence_item_id,
            evidence_file_id=claim.evidence_file_id,
            claim_id=claim.id,
            support_type=SupportType.PRIMARY.value,
            availability_status=LinkAvailability.AVAILABLE.value,
        )
    )

    claim.status = (
        ClaimStatus.CORRECTED.value
        if resolved is ReviewDecision.CORRECT
        else ClaimStatus.CONFIRMED.value
    )
    _emit(uow, case, claim, record, fact_version=version)
    uow.commit()

    _log.info(
        "claim.reviewed",
        case_id=str(case.id),
        claim_id=str(claim.id),
        claim_type=claim.claim_type,
        decision=resolved.value,
        review_mode=mode.value,
        # Never the value. A claim's value is a fragment of someone's document, and a
        # decision log is exactly where it should not come to rest.
        fact_version_id=str(version.id),
        fact_version_number=version.version_number,
    )
    return ReviewOutcome(claim=claim, decision=record, fact_version=version)


def _resolve(
    *,
    blind: bool,
    schema: ValueSchema,
    proposal: ProposedValue,
    entered_value: str | None,
    stated: ReviewDecision | None,
) -> tuple[ReviewDecision, ReviewMode, str | None]:
    """Work out which decision this was, and what value it authorises.

    For a blind field the decision is *derived* from what the person typed rather than
    stated by the client — which is what makes "confirm" and "correct" one interaction
    with an outcome nobody chose in advance.
    """
    if not blind:
        if stated is None:
            raise ValueError("a non-blind review must state its decision")
        if stated is ReviewDecision.REJECT:
            return stated, ReviewMode.PREFILLED, None
        # A pre-filled confirm authorises the proposal as it stands; a correction
        # authorises what the user typed instead.
        value = entered_value if stated is ReviewDecision.CORRECT else proposal.raw
        return stated, ReviewMode.PREFILLED, value

    if stated is ReviewDecision.REJECT:
        # A high-risk claim can still be rejected outright — "this date is not in this
        # document" is a real answer, and demanding a typed value for it would force
        # someone to invent one.
        return stated, ReviewMode.BLIND_ENTRY, None
    if entered_value is None:
        raise ValueError("a blind review must carry the value the user read")

    if schema is ValueSchema.DATE_V1:
        entered = parse_entered_date(entered_value)
        if entered is None:
            # The same formats the document normaliser accepts, on purpose. A person
            # typing `03/04/2025` is exactly as ambiguous as a document containing it,
            # and accepting it would let the interaction that exists to remove a guess
            # quietly reintroduce one.
            raise UnreadableEnteredValue(value=entered_value)
        matches = entered.isoformat() == proposal.model_iso or (
            normalise(proposal) == entered.isoformat()
        )
        raw = entered.isoformat()
    else:  # pragma: no cover - every high-risk type is a date today
        raw = " ".join(entered_value.split())
        matches = raw.casefold() == " ".join(proposal.raw.split()).casefold()

    return (
        ReviewDecision.CONFIRM if matches else ReviewDecision.CORRECT,
        ReviewMode.BLIND_ENTRY,
        raw,
    )


def _emit(
    uow: UnitOfWork,
    case: ApplicationCase,
    claim: ExtractedClaim,
    decision: ClaimReviewDecision,
    *,
    fact_version: FactVersion | None,
) -> None:
    from app.facts.events import ClaimReviewed

    uow.emit(
        ClaimReviewed(
            aggregate_id=claim.id,
            case_id=case.id,
            claim_type=claim.claim_type,
            decision=decision.decision,
            review_mode=decision.review_mode,
            fact_version_id=fact_version.id if fact_version else None,
        ),
        case_id=case.id,
        action="claim.reviewed",
        target_type="ExtractedClaim",
        target_id=claim.id,
    )


def list_pending(session: Session, *, case: ApplicationCase) -> list[ExtractedClaim]:
    """The review queue: claims nobody has decided about yet."""
    return ClaimRepository.list_pending_for_case(session, case_id=case.id)


def current_facts(session: Session, *, case: ApplicationCase) -> list[tuple[CaseFact, FactVersion]]:
    """The case's trusted values, one per fact, newest version only."""
    return FactRepository.current_for_case(session, case_id=case.id)
