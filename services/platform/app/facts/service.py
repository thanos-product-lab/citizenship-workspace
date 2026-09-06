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

from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.facts.domain import (
    HIGH_RISK_CLAIM_TYPES,
    JOURNEY_SCOPED_CLAIM_TYPES,
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
    CaseNotActive,
    ClaimAlreadyReviewed,
    ClaimNotFound,
    IncompleteReview,
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


def scope_key_for(claim: ExtractedClaim) -> str:
    """What the fact this claim authorises is *about*.

    Empty for a case-level fact — one grant date, one date of birth, whoever proposed
    them. `"<evidence_item_id>:<journey_index>"` for a travel claim, because a booking
    can describe two journeys and a case can hold two bookings, and all of them propose
    `travel.departure_date`.
    """
    if ClaimType(claim.claim_type) not in JOURNEY_SCOPED_CLAIM_TYPES:
        return ""
    return f"{claim.evidence_item_id}:{claim.journey_index}"


def _require_reviewable_document(session: Session, claim: ExtractedClaim) -> None:
    """Refuse a review of a claim whose document is on its way out.

    The case lock stops a deletion racing this command; this stops the sequential case
    the lock cannot see — a document already `DELETION_PENDING` while its case is fine.
    Blind confirmation asks the user to read the page and type what it says, so once
    access is blocked there is nothing to read, and a fact created here would be backed
    by a file nobody can open.

    A 404 rather than a 409: `get_active_for_case` already excludes a non-ACTIVE item,
    so from the client's point of view the document is gone.
    """
    from app.evidence.domain import EvidenceItem, EvidenceLifecycleStatus

    item = session.get(EvidenceItem, claim.evidence_item_id)
    if item is None or item.lifecycle_status is not EvidenceLifecycleStatus.ACTIVE:
        raise ClaimNotFound()


def _settle_document_if_done(
    session: Session, *, case: ApplicationCase, claim: ExtractedClaim
) -> None:
    """Move the document out of `AWAITING_CONFIRMATION` once nothing is left to decide.

    Split across two modules on purpose. *This* function answers the claims question,
    because `facts` owns claims; `evidence.service.mark_review_settled` answers the state
    question, because `evidence` owns `processing_status` and is the only place that can
    refuse the transition from a state a document should never be moving out of.

    The claim being decided is still in the session and may not be flushed, so it is
    excluded by id rather than trusted to have landed — otherwise the last field of a
    document would find itself still pending and the document would never settle.
    """
    from app.evidence import service as evidence_service

    remaining = [
        pending.id
        for pending in ClaimRepository.pending_for_evidence_item(
            session, case_id=case.id, evidence_item_id=claim.evidence_item_id
        )
        if pending.id != claim.id
    ]
    if remaining:
        return
    evidence_service.mark_review_settled(session, evidence_item_id=claim.evidence_item_id)


def review(
    session: Session,
    *,
    case: ApplicationCase,
    claim_id: uuid.UUID,
    user_id: str,
    entered_value: str | None = None,
    decision: ReviewDecision | None = None,
    reason_code: RejectionReason | None = None,
) -> ReviewOutcome:
    """Record a decision about one claim, and create the fact it authorises.

    `entered_value` is what the person typed. For a high-risk claim it is required and
    the decision is *derived* from it; for the rest the caller states the decision and
    `entered_value` carries a correction when there is one.
    """
    # Lock the case before reading anything, like every other case-scoped write command
    # (ADR-0005 R2). Both slice-3a reviews found this missing independently, and the
    # interleaving they describe is real: `mark_support_unavailable` reads the pending
    # claims, this command confirms one and creates a `FactEvidenceLink` marked
    # AVAILABLE, and the deletion then commits — leaving a destroyed document as live
    # support under a trusted fact. That is CLAUDE.md §9's *"deleting evidence cannot
    # leave its support state as available"*, broken by two transactions neither of
    # which is wrong on its own.
    #
    # `links.py` records the same lesson from M7: a first draft there checked the
    # lifecycle without locking, "which would have let a link be created against a case
    # whose deletion was already in flight — the one row deletion had already walked
    # past".
    locked = cases_service.lock_writable_case(session, case.id)
    if locked is None:
        raise ClaimNotFound()
    if locked.lifecycle_status is not LifecycleStatus.ACTIVE:
        # `require_case_access` filters DELETED only, so a DELETION_PENDING case reaches
        # here. Reviewing into one writes a trusted value and a name into tables the
        # purge is on its way to walk past.
        raise CaseNotActive(locked.lifecycle_status.value)

    # Read *after* the lock, and `FOR UPDATE`: two concurrent reviews of one claim both
    # read PENDING_REVIEW under READ COMMITTED, and `case_facts` had no unique key to
    # collide on, so one proposal produced two trusted facts with two different values.
    claim = ClaimRepository.get_for_update(session, case_id=case.id, claim_id=claim_id)
    if claim is None:
        raise ClaimNotFound()
    if ClaimStatus(claim.status) not in OPEN_STATUSES:
        # Deciding twice would either create a second fact from one proposal or
        # resurrect something already rejected. RFC §25: concurrency must not silently
        # overwrite review state.
        raise ClaimAlreadyReviewed(status=claim.status)

    _require_reviewable_document(session, claim)

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
    )
    session.add(record)
    # Flushed here, and this line is the boundary. `outcome()` needs `record.id`, which
    # only exists after the insert — so the decision is durable *before* anything can
    # produce the value a fact is built from.
    session.flush()

    uow = UnitOfWork(session, actor_id=user_id)

    if resolved is ReviewDecision.REJECT:
        claim.status = ClaimStatus.REJECTED.value
        # A rejection settles the claim as surely as a confirmation does. Leaving the
        # document waiting because the last field was rejected rather than confirmed
        # would make the state depend on *which* decision a person took, when what it
        # records is only whether they took one.
        _settle_document_if_done(session, case=case, claim=claim)
        _emit(uow, case, claim, record, fact_version=None)
        uow.commit()
        return ReviewOutcome(claim=claim, decision=record, fact_version=None)

    # The only call to `from_review` in the codebase, and it takes what `outcome()`
    # returns. Handing it the claim, or the claim's `proposed_value`, is a type error.
    reviewed = record.outcome(schema=schema)
    _fact, version = FactRepository.append_version(
        session,
        case_id=case.id,
        fact_type=claim.claim_type,
        scope_key=scope_key_for(claim),
        reviewed=reviewed,
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
    _settle_document_if_done(session, case=case, claim=claim)
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
            raise IncompleteReview("this field is reviewed with a stated decision")
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
        raise IncompleteReview("a blind review must carry the value you read")

    if schema is ValueSchema.DATE_V1:
        entered = parse_entered_date(entered_value)
        if entered is None:
            # The same formats the document normaliser accepts, on purpose. A person
            # typing `03/04/2025` is exactly as ambiguous as a document containing it,
            # and accepting it would let the interaction that exists to remove a guess
            # quietly reintroduce one.
            raise UnreadableEnteredValue(value=entered_value)
        # Compared against the *deterministic* reading only. Consulting `model_iso`
        # here was the one line in the product that read it, and `values.py` says three
        # times over that nothing does — but worse than the inconsistency is what it
        # decided: whether the fact's `source_method` says a human confirmed the model
        # or corrected it. On `09/04/2025` the shipped model guessed `2025-04-09`, the
        # normaliser correctly refused to read it, and a user typing 9 April would have
        # had their fact recorded as USER_CONFIRMED_AI_CLAIM — provenance set by a guess
        # the design says nothing reads.
        #
        # `normalise` returning None never matches, which is the honest outcome: there
        # was no reading of the proposal for a person to agree with, so the value is
        # theirs and the fact says USER_CORRECTED_AI_CLAIM.
        matches = normalise(proposal) == entered.isoformat()
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


def document_claims(
    session: Session, *, case: ApplicationCase, evidence_item_id: uuid.UUID
) -> list[tuple[ExtractedClaim, ClaimReviewDecision | None]]:
    """Every claim one document proposed, paired with the decision that settled it.

    Every status, not only the pending ones — this is the split view's data, and MVP
    §8.11 asks it to show confirmation history. A queue shows what is still open; a
    document shows what happened to it.

    The evidence item is resolved first, through `evidence.service`, so a document that
    was deleted or belongs to another case raises rather than returning an empty list.
    "This document has no claims" and "this is not your document" are different answers
    and a screen that cannot tell them apart will show the wrong one.
    """
    from app.evidence import service as evidence_service

    item, _file = evidence_service.get_evidence(
        session, case=case, evidence_item_id=evidence_item_id
    )
    claims = ClaimRepository.list_for_evidence_item(
        session, case_id=case.id, evidence_item_id=item.id
    )
    decisions = ClaimRepository.decisions_by_claim(
        session, case_id=case.id, claim_ids=[claim.id for claim in claims]
    )
    return [(claim, decisions.get(claim.id)) for claim in claims]


def list_pending(session: Session, *, case: ApplicationCase) -> list[ExtractedClaim]:
    """The review queue: claims nobody has decided about yet."""
    return ClaimRepository.list_pending_for_case(session, case_id=case.id)


def current_facts(session: Session, *, case: ApplicationCase) -> list[tuple[CaseFact, FactVersion]]:
    """The case's trusted values, one per fact, newest version only."""
    return FactRepository.current_for_case(session, case_id=case.id)
