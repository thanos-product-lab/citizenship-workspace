"""Pure-unit tests for the ApplicationCase state machine (no database).

These lock constraint (2): lifecycle transitions are guarded methods, and there is
no settable lifecycle column — the only path to ACTIVE is `activate()` from DRAFT.
"""

from datetime import UTC, datetime

import pytest

from app.cases.domain import ApplicationCase, CasePhase, LifecycleStatus, SupportStatus
from app.shared.errors import IllegalTransition


def _new_case() -> ApplicationCase:
    return ApplicationCase.create(owner_user_id="user_a", title="My case")


def test_new_case_starts_draft_unevaluated_setting_up() -> None:
    case = _new_case()
    assert case.lifecycle_status is LifecycleStatus.DRAFT
    assert case.support_status is SupportStatus.NOT_EVALUATED
    assert case.current_phase == CasePhase.SETTING_UP.value
    assert case.revision == 1


def test_lifecycle_status_has_no_setter() -> None:
    case = _new_case()
    with pytest.raises(AttributeError):
        case.lifecycle_status = LifecycleStatus.ACTIVE  # type: ignore[misc]


def test_activate_from_draft_reaches_active() -> None:
    case = _new_case()
    case.activate()
    assert case.lifecycle_status is LifecycleStatus.ACTIVE


def test_activate_is_refused_from_non_draft() -> None:
    case = _new_case()
    case.activate()
    with pytest.raises(IllegalTransition):
        case.activate()


def test_request_deletion_sets_pending_and_timestamp() -> None:
    case = _new_case()
    now = datetime.now(UTC)
    case.request_deletion(at=now)
    assert case.lifecycle_status is LifecycleStatus.DELETION_PENDING
    assert case.deletion_requested_at == now


def test_request_deletion_is_refused_when_already_pending() -> None:
    case = _new_case()
    case.request_deletion(at=datetime.now(UTC))
    with pytest.raises(IllegalTransition):
        case.request_deletion(at=datetime.now(UTC))
