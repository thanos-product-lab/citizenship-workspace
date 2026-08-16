"""Turning input links into something a person can read.

`AssessmentInputLink` records provenance **structurally**: an input kind, a version id, and
the field that was read. That is the right shape to store — it is exact, it cannot drift,
and it is what makes a conclusion reproducible. It is also, on its own, a list of UUIDs.

This module resolves those links against the versions they point at, so the requirement
detail screen can show *"Trip to Italy, 4 to 10 May 2026"* instead of
*"TRAVEL_RECORD_VERSION → 44300cde-…"*. It reads through the residence and applicants
**repositories** only — never their ORM internals — so the module boundary holds.

Two fields here carry most of the weight:

- **`is_still_current`** compares the linked version against its aggregate's current
  version. A stale result says *something* changed; this says *which input changed*.
- **`counts_as_confirmed`** is the §6.1 trust gate (ACTIVE + CONFIRMED + EXACT) —
  whether this record contributed to the **trusted** figure. Without it a list of twelve
  travel inputs reads as twelve pieces of corroboration, when it is twelve dates the user
  typed and some may not count at all. Volume must never read as evidence.

Resolution never invents. A version that cannot be found renders as an explicit
"no longer available" row rather than being dropped from the list — a provenance list
that silently omits an input it cannot explain is worse than one that admits the gap.
"""

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.applicants.domain import ReviewState as ProfileReviewState
from app.applicants.repository import RouteProfileRepository
from app.assessments.domain import AssessmentInputLink
from app.requirements.evaluation import LinkInputKind
from app.requirements.messages import format_date
from app.residence.domain import (
    DateConfidence,
    TravelLifecycleStatus,
    TravelReviewState,
    counts_toward_trusted_total,
)
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)

# Human labels for the route-profile fields a rule can name in `input_key`. The key is the
# contract; these labels are presentation, which is why they live here and not in the rule.
_PROFILE_FIELD_LABELS: dict[str, str] = {
    "date_of_birth": "Date of birth",
    "status_type": "Settled status",
    "status_granted_on": "Date status was granted",
    "married_to_british_citizen": "Married to a British citizen",
    "may_already_be_british": "May already be a British citizen",
}

_STATUS_LABELS: dict[str, str] = {
    "ILR": "Indefinite leave to remain",
    "ILE": "Indefinite leave to enter",
    "EU_SETTLED_STATUS": "EU settled status",
    "OTHER": "Other",
    "UNKNOWN": "Not stated",
}


@dataclass(frozen=True)
class ResolvedInput:
    """One versioned input a result read, described well enough to render."""

    input_kind: str
    input_key: str | None
    input_version_id: uuid.UUID
    contribution_role: str
    #: What this input is, e.g. "Trip to Italy" or "Date of birth".
    label: str
    #: The value as the rule read it, formatted for display.
    value: str
    #: An optional qualifying line, e.g. "Confirmed · exact dates".
    detail: str | None
    version_number: int | None
    #: Is this still the current version of its record? False means the input was edited.
    is_still_current: bool
    #: Did this input pass the §6.1 trust gate and count toward the trusted figure?
    #: None where the gate does not apply (the application date, profile answers).
    counts_as_confirmed: bool | None
    #: Design-system provenance token key (`tokens.ts`), for the badge.
    provenance_kind: str
    #: True when the version could not be loaded at all.
    unavailable: bool = False
    #: Has the record been removed since? A tombstone keeps `current_version_id` pointing
    #: at its last version, so removal is invisible to `is_still_current` and must be its
    #: own signal — otherwise a deleted trip renders as a live, counting input.
    is_removed: bool = False


def resolve_input_links(session: Session, links: list[AssessmentInputLink]) -> list[ResolvedInput]:
    """Resolve each link, preserving the order the result recorded them in."""
    return [_resolve(session, link) for link in links]


def _resolve(session: Session, link: AssessmentInputLink) -> ResolvedInput:
    if link.input_kind == LinkInputKind.APPLICATION_DATE_VERSION.value:
        return _resolve_application_date(session, link)
    if link.input_kind == LinkInputKind.TRAVEL_RECORD_VERSION.value:
        return _resolve_travel_record(session, link)
    if link.input_kind == LinkInputKind.ROUTE_PROFILE_VERSION.value:
        return _resolve_route_profile(session, link)
    return _unavailable(link, label="Unrecognised input")


def _unavailable(link: AssessmentInputLink, *, label: str) -> ResolvedInput:
    """A link we cannot describe. Kept in the list and labelled, never dropped."""
    return ResolvedInput(
        input_kind=link.input_kind,
        input_key=link.input_key,
        input_version_id=link.input_version_id,
        contribution_role=link.contribution_role,
        label=label,
        value="No longer available",
        detail="This input was recorded on the assessment but cannot be read now.",
        version_number=None,
        is_still_current=False,
        counts_as_confirmed=None,
        provenance_kind="unavailable",
        unavailable=True,
    )


def _resolve_application_date(session: Session, link: AssessmentInputLink) -> ResolvedInput:
    version = ProposedApplicationDateRepository.get_version(session, link.input_version_id)
    if version is None:
        return _unavailable(link, label="Proposed application date")
    return ResolvedInput(
        input_kind=link.input_kind,
        input_key=link.input_key,
        input_version_id=link.input_version_id,
        contribution_role=link.contribution_role,
        label="Proposed application date",
        value=format_date(version.application_date),
        detail=f"Version {version.version_number}",
        version_number=version.version_number,
        is_still_current=ProposedApplicationDateRepository.is_current_version(
            session, link.input_version_id
        ),
        # The trust gate is about travel records; the application date is a direct
        # user choice, so "confirmed" does not apply to it.
        counts_as_confirmed=None,
        provenance_kind="user_confirmed",
    )


def _resolve_travel_record(session: Session, link: AssessmentInputLink) -> ResolvedInput:
    found = TravelRecordRepository.get_record_for_version(session, link.input_version_id)
    if found is None:
        return _unavailable(link, label="Travel record")
    record, version = found

    confirmed = version.review_state == TravelReviewState.CONFIRMED.value
    removed = record.lifecycle_status is TravelLifecycleStatus.REMOVED
    # One definition of the §6.1 gate, shared with the assessment service. It includes the
    # ACTIVE check, which is what stops a removed record reporting as counting.
    counts = counts_toward_trusted_total(record, version)

    return ResolvedInput(
        input_kind=link.input_kind,
        input_key=link.input_key,
        input_version_id=link.input_version_id,
        contribution_role=link.contribution_role,
        label=f"Trip to {version.destination_label}",
        value=_trip_dates(version.departure_date, version.return_date),
        detail=_trip_detail(confirmed=confirmed, date_confidence=version.date_confidence),
        version_number=version.version_number,
        is_still_current=record.current_version_id == link.input_version_id,
        is_removed=removed,
        counts_as_confirmed=counts,
        provenance_kind=_travel_provenance(
            removed=removed, confirmed=confirmed, date_confidence=version.date_confidence
        ),
    )


def _travel_provenance(*, removed: bool, confirmed: bool, date_confidence: str) -> str:
    """How this record's value came to be — *not* whether it counted.

    The two are separate questions and the row answers them separately: this badge
    describes provenance, while "Did not count towards the confirmed figure" states the
    §6.1 outcome. Conflating them produced false labels: a deleted record read as
    "Corrected" (the user deleted it, they did not correct it) and a user-typed estimated
    date read as "Calculated" (nothing calculated it).

    A record the user confirmed is `user_confirmed` even when its dates are estimated —
    they did confirm it; the date confidence is a different axis and is shown on its own
    line. Only a record that was never confirmed lacks an honest token, because the
    provenance vocabulary (DESIGN_SYSTEM_FOUNDATIONS §4) has no "user entered, not yet
    confirmed" kind. `unavailable` is the least-wrong of the eight and the row says the
    rest in words; adding a kind is a design-system change, not a thing to do silently.
    """
    if date_confidence == DateConfidence.CONFLICTING.value:
        return "conflicting"
    if removed:
        # Accurate rather than merely convenient: the record is genuinely gone. A version
        # that could not be *read* carries `unavailable=True` as well, so the two stay
        # distinguishable structurally and in the row's own wording.
        return "unavailable"
    if confirmed:
        return "user_confirmed"
    return "unavailable"


def _resolve_route_profile(session: Session, link: AssessmentInputLink) -> ResolvedInput:
    version = RouteProfileRepository.get_version(session, link.input_version_id)
    if version is None:
        return _unavailable(link, label="Route profile")

    is_current = RouteProfileRepository.is_current_version(session, link.input_version_id)
    common = {
        "input_kind": link.input_kind,
        "input_key": link.input_key,
        "input_version_id": link.input_version_id,
        "contribution_role": link.contribution_role,
        "version_number": version.version_number,
        "is_still_current": is_current,
        "counts_as_confirmed": None,
        # Derived, not asserted: a profile version can still be DRAFT, and the badge must
        # not outrun the domain even where the current write paths make that unreachable.
        "provenance_kind": (
            "user_confirmed"
            if version.review_state == ProfileReviewState.CONFIRMED.value
            else "system_calculated"
        ),
    }

    # A rule that names no field read the profile as a whole (the composite route guard).
    if link.input_key is None:
        return ResolvedInput(
            label="Your route answers",
            value="Answers given during setup",
            detail=f"Version {version.version_number}",
            **common,  # type: ignore[arg-type]
        )

    label = _PROFILE_FIELD_LABELS.get(link.input_key, link.input_key.replace("_", " "))
    return ResolvedInput(
        label=label,
        value=_profile_value(version, link.input_key),
        detail=f"Version {version.version_number}",
        **common,  # type: ignore[arg-type]
    )


# --- value formatting -------------------------------------------------------


def _trip_dates(departure: date, return_: date) -> str:
    return f"{format_date(departure)} to {format_date(return_)}"


def _trip_detail(*, confirmed: bool, date_confidence: str) -> str:
    """The two independent axes of a travel record (§11.4, §11.5), stated plainly. These
    are what decide whether the record counted, so they are never hidden behind a badge."""
    review = "Confirmed" if confirmed else "Not confirmed"
    confidence = {
        DateConfidence.EXACT.value: "exact dates",
        DateConfidence.ESTIMATED.value: "estimated dates",
        DateConfidence.UNKNOWN.value: "dates not known",
        DateConfidence.CONFLICTING.value: "conflicting dates",
    }.get(date_confidence, date_confidence.lower())
    return f"{review} · {confidence}"


def _profile_value(version: object, field: str) -> str:
    """The profile field's value, formatted. An unanswered field says so rather than
    rendering as blank — a missing answer is information, not an empty string."""
    raw = getattr(version, field, None)
    if raw is None:
        return "Not answered"
    if isinstance(raw, bool):
        return "Yes" if raw else "No"
    if isinstance(raw, date):
        return format_date(raw)
    if field == "status_type":
        return _STATUS_LABELS.get(str(raw), str(raw))
    return str(raw)
