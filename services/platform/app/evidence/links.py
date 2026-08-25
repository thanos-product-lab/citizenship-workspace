"""Attaching a document to a trip, and what that means to an assessment.

Domain §11.9, ADR-0021. This is where evidence first touches the assessment path, so two
boundaries are worth stating before the code.

**What a link asserts, and what it does not.** A link is the *user* saying "this document
is for that trip". Nothing here opens the document, and no rule that reads these links
looks at what the document says. `residence.travel_consistency` asks "is this trip
evidenced?" and stops. "Is this the right evidence?" needs a model, and answering it
without one — by matching a booking's dates against the trip's, say — would be a
deterministic guess dressed as a check, which is exactly the false reassurance directive 7
exists to prevent. That question is M8's.

**Why this lives in `evidence/` when the command reads as a travel-record command.** The
route hangs off the travel record, because the user's sentence starts with the trip. The
service lives here because the link's *lifecycle* is governed by the document: slice 5
deletes a document and every link pointing at it has to be withdrawn in the same
transaction. Keeping `mark_support_unavailable` next to the code that creates links is
what stops that from becoming a call site someone forgets.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.assessments.invalidation import StaleReason, invalidate_for_input_change
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.evidence.domain import (
    EvidenceAttachedToTravelRecord,
    EvidenceDetachedFromTravelRecord,
    EvidenceItem,
    EvidenceProcessingStatus,
    EvidenceTravelLink,
    LinkAvailability,
    utcnow,
)
from app.evidence.repository import EvidenceLinkRepository, EvidenceRepository
from app.requirements.models import DependencyInputKind
from app.residence.domain import TravelLifecycleStatus, TravelRecord
from app.residence.repository import TravelRecordRepository
from app.shared.errors import (
    CaseNotActive,
    EvidenceLinkNotFound,
    EvidenceNotAttachable,
    EvidenceNotFound,
    TravelRecordNotFound,
)
from app.shared.unit_of_work import UnitOfWork

#: Processing states a document may be attached from.
#:
#: Everything except the in-flight ones. `FAILED` and `UNSUPPORTED` are deliberately
#: included: the user may know perfectly well what is in a scan the parser could not read,
#: and the link is their assertion about their own document, not the machine's verdict on
#: it. Refusing to let them attach it would make extraction success a precondition for
#: saying "this is my booking", which it is not.
#:
#: The in-flight states are excluded for a different reason — not judgement but stability.
#: A document attached mid-read would have its coverage state settle underneath the user
#: seconds later, and a support state that changes on its own is one nobody can act on.
_UNATTACHABLE_STATUSES = frozenset(
    {
        EvidenceProcessingStatus.VALIDATING,
        EvidenceProcessingStatus.EXTRACTING_TEXT,
        EvidenceProcessingStatus.ANALYSING,
    }
)


@dataclass(frozen=True)
class LinkOutcome:
    link: EvidenceTravelLink
    #: Whether this call changed anything. False when the link already existed (attach) —
    #: the caller answers 200 either way, because the user's intent is satisfied.
    changed: bool


def attach_to_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
) -> LinkOutcome:
    """Record that a document supports a trip.

    Both endpoints are re-resolved inside this case. RLS hides other tenants but not the
    caller's own other cases (Domain §3.1), so "is this trip mine?" and "is this document
    mine?" are two explicit checks, not one assumption — and a link is exactly the shape
    that could otherwise smuggle a row across a case boundary.
    """
    _require_active_case(session, case)
    record = _load_record(session, case, travel_record_id)
    item = _load_attachable_item(session, case, evidence_item_id)

    existing = EvidenceLinkRepository.live_between(
        session,
        case_id=case.id,
        travel_record_id=record.id,
        evidence_item_id=item.id,
    )
    if existing is not None:
        # Already attached. Not an error: the user asked for a state that already holds,
        # and nothing about the case changed, so nothing is emitted and nothing is staled.
        # Emitting anyway would put a lie in `domain_events` and restale a result for a
        # change that did not happen.
        return LinkOutcome(link=existing, changed=False)

    link = EvidenceTravelLink.attach(
        case_id=case.id,
        travel_record_id=record.id,
        evidence_item_id=item.id,
        at=utcnow(),
    )
    EvidenceLinkRepository.add(session, link)
    session.flush()  # the link needs an id before the event carries it

    _emit_and_invalidate(
        session,
        user,
        case_id=case.id,
        travel_record_id=record.id,
        event=EvidenceAttachedToTravelRecord(
            aggregate_id=record.id,
            case_id=case.id,
            evidence_item_id=item.id,
            link_id=link.id,
        ),
        action="evidence.attached_to_travel_record",
    )
    return LinkOutcome(link=link, changed=True)


def detach_from_travel_record(
    session: Session,
    *,
    case: ApplicationCase,
    user: CurrentUser,
    travel_record_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
) -> LinkOutcome:
    """Withdraw a document's support for a trip.

    The row is kept and its availability set to `UNAVAILABLE` — not `DELETED`, which slice
    5 reserves for "the document itself is gone". A historical assessment linked this row
    and has to keep resolving to something that can say what it read (§22.3).

    Unlike attach, a no-op here is an error. Asking to detach something that is not
    attached means the caller's picture of the case is wrong, and answering 200 would
    confirm a state that was never true.
    """
    _require_active_case(session, case)
    record = _load_record(session, case, travel_record_id)

    link = EvidenceLinkRepository.live_between(
        session,
        case_id=case.id,
        travel_record_id=record.id,
        evidence_item_id=evidence_item_id,
    )
    if link is None:
        raise EvidenceLinkNotFound()

    link.withdraw(availability=LinkAvailability.UNAVAILABLE, at=utcnow())

    _emit_and_invalidate(
        session,
        user,
        case_id=case.id,
        travel_record_id=record.id,
        event=EvidenceDetachedFromTravelRecord(
            aggregate_id=record.id,
            case_id=case.id,
            evidence_item_id=evidence_item_id,
            link_id=link.id,
            availability=LinkAvailability.UNAVAILABLE.value,
        ),
        action="evidence.detached_from_travel_record",
    )
    return LinkOutcome(link=link, changed=True)


def mark_support_unavailable(
    session: Session,
    uow: UnitOfWork,
    *,
    case_id: uuid.UUID,
    evidence_item_id: uuid.UUID,
    at: datetime,
) -> int:
    """Withdraw every link pointing at a document, because the document is going away.

    **The single seam for step 4 of Domain §51.1** ("mark support links unavailable"), and
    it exists as one function before it has two callers on purpose. At M7 the only link
    kind is `EvidenceTravelLink`. At M8, `FactEvidenceLink` arrives and step 4 needs a
    second call — which is a line added *inside here*, next to the first, rather than a
    call site somewhere in the deletion command that whoever writes M8 has to know exists.

    Takes the caller's `UnitOfWork` rather than making its own: this runs inside the
    deletion command's transaction, and support becoming unavailable has to commit with
    the deletion or not at all.

    Returns how many links were withdrawn, so the caller can skip invalidation when the
    document supported nothing.
    """
    links = EvidenceLinkRepository.live_for_evidence_item(
        session, case_id=case_id, evidence_item_id=evidence_item_id
    )
    for link in links:
        link.withdraw(availability=LinkAvailability.DELETED, at=at)
        uow.emit(
            EvidenceDetachedFromTravelRecord(
                aggregate_id=link.travel_record_id,
                case_id=case_id,
                evidence_item_id=evidence_item_id,
                link_id=link.id,
                availability=LinkAvailability.DELETED.value,
            ),
            case_id=case_id,
            action="evidence.support_withdrawn_on_deletion",
            target_type="TravelRecord",
            target_id=link.travel_record_id,
        )
    # M8: FactEvidenceLink availability is withdrawn here too.
    return len(links)


def coverage_for_case(session: Session, *, case_id: uuid.UUID) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Which documents currently evidence which trips.

    Keyed by travel *record* id, matching what the links point at, and containing only
    records that have at least one live link — an absent key means "no coverage", which
    is what the rule tests. Returning an entry with an empty list for every trip would
    require reading the trips, and this function has no business knowing which trips
    exist.
    """
    coverage: dict[uuid.UUID, list[uuid.UUID]] = {}
    for link in EvidenceLinkRepository.live_for_case(session, case_id=case_id):
        coverage.setdefault(link.travel_record_id, []).append(link.evidence_item_id)
    return coverage


def _require_active_case(session: Session, case: ApplicationCase) -> None:
    """Lock the case row, then confirm it is ACTIVE.

    The same guard the residence writes use, and for the same reason: the lock serialises
    against a concurrent deletion (ADR-0005 R2). A first draft here checked the
    lifecycle without locking, which would have let a link be created against a case
    whose deletion was already in flight — the one row deletion had already walked past.
    """
    locked = cases_service.lock_writable_case(session, case.id)
    status = locked.lifecycle_status if locked is not None else case.lifecycle_status
    if status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(status.value)


def _load_record(
    session: Session, case: ApplicationCase, travel_record_id: uuid.UUID
) -> TravelRecord:
    """The trip, only if it is this case's and still active.

    A removed trip is refused: it is excluded from every total and every rule, so
    evidencing it would create a link no assessment will ever read and a support state
    on a row the user has already deleted.
    """
    record = TravelRecordRepository.get(session, travel_record_id)
    if (
        record is None
        or record.case_id != case.id
        or record.lifecycle_status is not TravelLifecycleStatus.ACTIVE
    ):
        raise TravelRecordNotFound()
    return record


def _load_attachable_item(
    session: Session, case: ApplicationCase, evidence_item_id: uuid.UUID
) -> EvidenceItem:
    item = EvidenceRepository.get_active_for_case(
        session, case_id=case.id, evidence_item_id=evidence_item_id
    )
    if item is None:
        raise EvidenceNotFound()
    status = EvidenceProcessingStatus(item.processing_status)
    if status in _UNATTACHABLE_STATUSES:
        raise EvidenceNotAttachable(status.value)
    return item


def _emit_and_invalidate(
    session: Session,
    user: CurrentUser,
    *,
    case_id: uuid.UUID,
    travel_record_id: uuid.UUID,
    event: EvidenceAttachedToTravelRecord | EvidenceDetachedFromTravelRecord,
    action: str,
) -> None:
    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        event,
        case_id=case_id,
        action=action,
        target_type="TravelRecord",
        target_id=travel_record_id,
    )
    # `EVIDENCE_SUPPORT`, not `TRAVEL_RECORD`. The fan-out is one requirement
    # (`residence.travel_consistency`), and that narrowness is deliberate: attaching a
    # booking does not change how many days the user was absent, so
    # `residence.total_absences` and the physical-presence date must stay current.
    # Widening this to TRAVEL_RECORD would restale the whole residence group on every
    # upload and teach the user their totals are less stable than they are.
    invalidate_for_input_change(
        session,
        uow,
        case_id=case_id,
        input_kind=DependencyInputKind.EVIDENCE_SUPPORT,
        reason_code=StaleReason.EVIDENCE_SUPPORT_CHANGED,
    )
    uow.commit()
