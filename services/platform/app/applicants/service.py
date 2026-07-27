"""Route-profile onboarding commands. Domain logic lives here, not in the routes.

Two commands:

- `save_draft` edits the working DRAFT in place. If the current version is CONFIRMED
  (a previous confirm), it starts a *new* draft rather than mutating the immutable
  confirmed version (§9.4). The profile's optimistic-concurrency token advances on
  every save — the answers live on the child version row, so the save flags the
  profile modified to make `version_id_col` engage.
- `confirm_route_profile` snapshots the draft into an immutable CONFIRMED version
  (confirming *creates* a version, never an update), evaluates the three route rules,
  projects the composite conclusion onto the case's support status, and — only when
  supported — activates the case. State + `RouteProfileConfirmed` +
  `RouteSupportEvaluated` + audit + outbox commit atomically.

Both commands require the case to be a DRAFT: onboarding is not editable or
confirmable once the case has been activated or is pending deletion.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.applicants.domain import (
    ReviewState,
    RouteProfile,
    RouteProfileConfirmed,
    RouteProfileDraftSaved,
    RouteProfileVersion,
    StatusType,
)
from app.applicants.repository import RouteProfileRepository
from app.applicants.schemas import RouteProfileDraftInput
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, LifecycleStatus, RouteSupportEvaluated, SupportStatus
from app.requirements.domain import Conclusion
from app.requirements.route_rules import RouteSupportDecision, evaluate_route_support
from app.shared.errors import ConcurrencyConflict, IllegalTransition, ProfileIncomplete
from app.shared.unit_of_work import UnitOfWork

# Composite conclusion → case support status (approved M2 plan, decision #4).
# A conclusion the product cannot definitively resolve (missing data) maps to
# NOT_EVALUATED, never to a definitive negative — visible uncertainty over false
# reassurance (§2.7).
_SUPPORT_BY_CONCLUSION: dict[Conclusion, SupportStatus] = {
    Conclusion.SUPPORTED: SupportStatus.SUPPORTED,
    Conclusion.REQUIRES_JUDGEMENT: SupportStatus.REQUIRES_REVIEW,
    Conclusion.PROFESSIONAL_REVIEW_RECOMMENDED: SupportStatus.UNSUPPORTED,
    Conclusion.NOT_CURRENTLY_SATISFIED: SupportStatus.UNSUPPORTED,
    Conclusion.NOT_YET_ASSESSED: SupportStatus.NOT_EVALUATED,
}

_SUPPORTED_STATUS_TYPES = {
    StatusType.ILR.value,
    StatusType.ILE.value,
    StatusType.EU_SETTLED_STATUS.value,
}


@dataclass(frozen=True)
class ConfirmOutcome:
    decision: RouteSupportDecision
    support: SupportStatus
    case: ApplicationCase
    confirmed: RouteProfileVersion


def get_draft(
    session: Session, *, case: ApplicationCase
) -> tuple[RouteProfile, RouteProfileVersion] | None:
    """Return the case's route profile and its current version, or None if not started."""
    profile = RouteProfileRepository.get_for_case(session, case.id)
    if profile is None or profile.current_version_id is None:
        return None
    version = RouteProfileRepository.get_version(session, profile.current_version_id)
    if version is None:
        return None
    return profile, version


def save_draft(
    session: Session, *, case: ApplicationCase, user: CurrentUser, answers: RouteProfileDraftInput
) -> tuple[RouteProfile, RouteProfileVersion]:
    _require_draft_case(session, case, "route onboarding is not editable")

    profile = RouteProfileRepository.get_for_case(session, case.id)
    if profile is None:
        profile = RouteProfile.start(case_id=case.id)
        RouteProfileRepository.add_profile(session, profile)
        session.flush()
    else:
        _check_revision(profile, answers.expected_revision)

    version = _editable_draft(session, profile, created_by=user.user_id)
    _apply_answers(version, answers)
    _advance_profile(profile, version)

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        RouteProfileDraftSaved(
            aggregate_id=profile.id,
            version_number=version.version_number,
            answered_fields=tuple(version.answered_fields),
        ),
        case_id=case.id,
        action="route_profile.draft_saved",
        target_type="RouteProfileVersion",
        target_id=version.id,
    )
    uow.commit()
    session.refresh(profile)
    return profile, version


def confirm_route_profile(
    session: Session, *, case: ApplicationCase, user: CurrentUser, expected_revision: int | None
) -> ConfirmOutcome:
    _require_draft_case(session, case, "the case is not open for confirmation")

    profile = RouteProfileRepository.get_for_case(session, case.id)
    if profile is None or profile.current_version_id is None:
        raise IllegalTransition("there is no route profile to confirm")
    _check_revision(profile, expected_revision)

    draft = RouteProfileRepository.get_version(session, profile.current_version_id)
    if draft is None or draft.review_state != ReviewState.DRAFT.value:
        # Already confirmed with no newer edits — edit answers to re-confirm.
        raise IllegalTransition("there is no draft to confirm")

    missing = _missing_required_fields(draft)
    if missing:
        raise ProfileIncomplete(missing)

    confirmed = draft.confirmed_copy(created_by=user.user_id)
    RouteProfileRepository.add_version(session, confirmed)
    _advance_profile(profile, confirmed)

    reference_date = date.today()  # clock read here, never inside the pure rule
    decision = evaluate_route_support(
        date_of_birth=confirmed.date_of_birth,
        status_type=confirmed.status_type,
        married_to_british_citizen=confirmed.married_to_british_citizen,
        may_already_be_british=confirmed.may_already_be_british,
        reference_date=reference_date,
        profile_confirmed=True,
    )
    support = _SUPPORT_BY_CONCLUSION[decision.composite.conclusion]
    case.record_route_support(support)  # activates the case iff SUPPORTED

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        RouteProfileConfirmed(
            aggregate_id=profile.id,
            version_number=confirmed.version_number,
            version_id=str(confirmed.id),
        ),
        case_id=case.id,
        action="route_profile.confirmed",
        target_type="RouteProfileVersion",
        target_id=confirmed.id,
    )
    uow.emit(
        RouteSupportEvaluated(
            aggregate_id=case.id,
            support_status=support.value,
            composite_conclusion=decision.composite.conclusion.value,
            adult_conclusion=decision.adult.conclusion.value,
            status_conclusion=decision.status.conclusion.value,
            summary_code=decision.composite.summary_code,
            route_profile_version_id=str(confirmed.id),
            reference_date=reference_date.isoformat(),
            rule_set=decision.rule_set,
            semantic_version=decision.semantic_version,
        ),
        case_id=case.id,
        action="route_support.evaluated",
        target_type="ApplicationCase",
        target_id=case.id,
    )
    uow.commit()
    session.refresh(case)
    return ConfirmOutcome(decision=decision, support=support, case=case, confirmed=confirmed)


# --- helpers ---------------------------------------------------------------


def _require_draft_case(session: Session, case: ApplicationCase, message: str) -> None:
    """Lock the case row and confirm it is still a DRAFT before writing. The lock
    serialises against a concurrent deletion so a write cannot land on a case that
    has since become DELETION_PENDING (ADR-0005 R2)."""
    locked = cases_service.lock_writable_case(session, case.id)
    status = locked.lifecycle_status if locked is not None else case.lifecycle_status
    if status is not LifecycleStatus.DRAFT:
        raise IllegalTransition(f"{message} while the case is {status}")


def _editable_draft(
    session: Session, profile: RouteProfile, *, created_by: str
) -> RouteProfileVersion:
    """The current DRAFT version, or a fresh one when there is none or the current
    version is CONFIRMED (editing a confirmed version creates a new version, §9.4)."""
    current = (
        RouteProfileRepository.get_version(session, profile.current_version_id)
        if profile.current_version_id is not None
        else None
    )
    if current is not None and current.review_state == ReviewState.DRAFT.value:
        return current
    draft = RouteProfileVersion.new_draft(
        route_profile_id=profile.id,
        created_by=created_by,
        version_number=(current.version_number + 1) if current else 1,
        supersedes_version_id=current.id if current else None,
    )
    RouteProfileRepository.add_version(session, draft)
    session.flush()
    return draft


def _advance_profile(profile: RouteProfile, version: RouteProfileVersion) -> None:
    # Point at the current version and force the aggregate's concurrency token to
    # advance even when only the child version row's columns changed.
    profile.current_version_id = version.id
    flag_modified(profile, "current_version_id")


def _check_revision(profile: RouteProfile, expected: int | None) -> None:
    # Fast, explicit conflict feedback; version_id_col is the ultimate guard on commit.
    if expected is not None and expected != profile.revision:
        raise ConcurrencyConflict()


def _apply_answers(version: RouteProfileVersion, answers: RouteProfileDraftInput) -> None:
    version.date_of_birth = answers.date_of_birth
    version.status_type = answers.status_type.value if answers.status_type else None
    version.status_granted_on = answers.status_granted_on
    version.married_to_british_citizen = answers.married_to_british_citizen
    version.may_already_be_british = answers.may_already_be_british


def _missing_required_fields(draft: RouteProfileVersion) -> list[str]:
    """Answers required before a profile can be confirmed. `status_granted_on` is
    required only for the supported status types (§9.4)."""
    missing: list[str] = []
    if draft.date_of_birth is None:
        missing.append("date_of_birth")
    if draft.status_type is None or draft.status_type == StatusType.UNKNOWN.value:
        missing.append("status_type")
    elif draft.status_type in _SUPPORTED_STATUS_TYPES and draft.status_granted_on is None:
        missing.append("status_granted_on")
    if draft.married_to_british_citizen is None:
        missing.append("married_to_british_citizen")
    if draft.may_already_be_british is None:
        missing.append("may_already_be_british")
    return missing
