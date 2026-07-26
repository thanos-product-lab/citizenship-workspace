"""Route-profile onboarding commands. Domain logic lives here, not in the routes.

`save_draft` is the reference for how a child-row edit still respects the parent
aggregate's optimistic concurrency:

1. The draft answers live on the DRAFT `RouteProfileVersion`, edited in place.
2. But the concurrency token is the *profile's* `revision`. So each save flags the
   profile modified (`flag_modified`), forcing SQLAlchemy's `version_id_col` to
   issue an UPDATE that checks-and-bumps `revision`. A stale token → 409.
3. State + `RouteProfileDraftSaved` event + audit + outbox commit atomically.

A draft may only be edited while the case is a DRAFT: onboarding does not reopen on
a case that has been activated or is pending deletion.
"""

import uuid

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.applicants.domain import RouteProfile, RouteProfileDraftSaved, RouteProfileVersion
from app.applicants.repository import RouteProfileRepository
from app.applicants.schemas import RouteProfileDraftInput
from app.auth.schemas import CurrentUser
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.shared.errors import ConcurrencyConflict, IllegalTransition
from app.shared.unit_of_work import UnitOfWork


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
    if case.lifecycle_status is not LifecycleStatus.DRAFT:
        raise IllegalTransition(
            f"route onboarding is not editable while the case is {case.lifecycle_status}"
        )

    profile = RouteProfileRepository.get_for_case(session, case.id)
    if profile is None:
        profile, version = _start_profile(session, case_id=case.id, created_by=user.user_id)
    else:
        _check_revision(profile, answers.expected_revision)
        version = _require_draft_version(session, profile)

    _apply_answers(version, answers)

    # Advance the aggregate's concurrency token even though only the child row's
    # columns changed: flagging the profile modified makes version_id_col fire.
    profile.current_version_id = version.id
    flag_modified(profile, "current_version_id")

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


def _start_profile(
    session: Session, *, case_id: uuid.UUID, created_by: str
) -> tuple[RouteProfile, RouteProfileVersion]:
    profile = RouteProfile.start(case_id=case_id)
    RouteProfileRepository.add_profile(session, profile)
    version = RouteProfileVersion.new_draft(route_profile_id=profile.id, created_by=created_by)
    RouteProfileRepository.add_version(session, version)
    session.flush()  # assign ids before the pointer is set
    return profile, version


def _require_draft_version(session: Session, profile: RouteProfile) -> RouteProfileVersion:
    version = (
        RouteProfileRepository.get_version(session, profile.current_version_id)
        if profile.current_version_id is not None
        else None
    )
    if version is None:  # a profile row without its draft version is a broken invariant
        raise IllegalTransition("route profile has no current draft version")
    return version


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
