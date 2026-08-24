"""A failed recalculation leaves the safe state, and says so (Domain §41.4).

Before this slice `recalculate` had no `try`. A failure propagated, the transaction rolled
back, and *nothing survived*: no run row, no issue, no record of any kind. The user saw a
banner that a reload erased, next to stale conclusions with nothing explaining why they had
not been refreshed. Silence and success looked identical, which is the shape of every
false-reassurance defect in this product.

Three things are asserted throughout, in decreasing order of how badly they matter:

1. **Nothing is promoted.** A failed run must not replace, supersede, or refresh any result
   (`CLAUDE.md` §9: "a failed recalculation cannot replace the last historical result").
2. **The failure is durable and legible.** A FAILED run row and a `PROCESSING_FAILURE`
   issue that survive the request.
3. **The recovery never eats the original error.** It runs inside an `except`; an exception
   thrown from there replaces the cause an engineer needs.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments import service as assessments_service
from app.assessments.domain import (
    AssessmentMode,
    AssessmentResult,
    AssessmentRun,
    AssessmentRunStatus,
    AssessmentTriggerType,
    RecalculationFailureCode,
)
from app.assessments.repository import AssessmentRepository
from app.issues.domain import Issue, IssueResolution, IssueStatus, IssueType
from app.requirements.domain import Currency
from app.shared.db import Base, get_sessionmaker
from app.shared.errors import ConcurrencyConflict
from app.shared.tenant import set_tenant

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}

#: A synthetic marker planted in an exception message. Nothing that reads like case data
#: may reach a persisted column — this stands in for a destination label or a date of birth
#: arriving inside a driver error's rendering of its bound parameters.
PII_MARKER = "SYNTHETIC-LEAK-CANARY"


def _assessed_case(api: Api, user: str = "user_a") -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    return case_id


def _add_trip(api: Api, case_id: str, dep: str, ret: str, user: str = "user_a") -> None:
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records",
        json={
            "destination_label": "Trip",
            "departure_date": dep,
            "return_date": ret,
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
        },
    )


@pytest.fixture
def break_persistence(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Make `recalculate` fail *after* it has written some results.

    Failing before the first write would prove far less: the interesting claim is that a
    half-written run leaves nothing behind, and that needs a half-written run.
    """
    original = assessments_service._persist_result

    def install(*, after: int = 3, exc: BaseException | None = None) -> None:
        state = {"calls": 0}

        def failing(*args: Any, **kwargs: Any) -> None:
            state["calls"] += 1
            if state["calls"] > after:
                raise exc or RuntimeError(f"evaluator exploded on {PII_MARKER}")
            original(*args, **kwargs)

        monkeypatch.setattr(assessments_service, "_persist_result", failing)

    return install


@pytest.fixture
def snapshot(db_session: Session) -> Callable[[str], dict[uuid.UUID, tuple[str, str]]]:
    """Every non-superseded result for a case, as id → (conclusion, currency)."""

    def take(case_id: str) -> dict[uuid.UUID, tuple[str, str]]:
        rows = db_session.scalars(
            select(AssessmentResult).where(
                AssessmentResult.case_id == uuid.UUID(case_id),
                AssessmentResult.currency != Currency.SUPERSEDED.value,
            )
        )
        return {row.id: (row.conclusion, row.currency) for row in rows}

    return take


def _runs(session: Session, case_id: str) -> list[AssessmentRun]:
    """Every run for the case, oldest finished first.

    Ordered by `completed_at`, not `started_at`, for the reason `get_latest_finished_run`
    documents: `started_at` is a Postgres transaction timestamp and does not order the way
    a reader assumes.
    """
    return list(
        session.scalars(
            select(AssessmentRun)
            .where(AssessmentRun.case_id == uuid.UUID(case_id))
            .order_by(AssessmentRun.completed_at)
        )
    )


def _issues(session: Session, case_id: str, issue_type: IssueType) -> list[Issue]:
    return list(
        session.scalars(
            select(Issue).where(
                Issue.case_id == uuid.UUID(case_id),
                Issue.issue_type == issue_type.value,
            )
        )
    )


def _queue(api: Api, case_id: str, user: str = "user_a") -> dict[str, Any]:
    payload: dict[str, Any] = api(user).get(f"/api/v1/cases/{case_id}/issues").json()
    return payload


# --- 1. nothing is promoted ------------------------------------------------


def test_a_failed_recalculation_cannot_replace_the_last_historical_result(
    api: Api,
    db_session: Session,
    break_persistence: Callable[..., None],
    snapshot: Callable[[str], dict[uuid.UUID, tuple[str, str]]],
) -> None:
    """The `CLAUDE.md` §9 invariant, stated directly.

    Not "the conclusions look the same" — the same *result rows*, with the same ids. A run
    that superseded them and wrote identical replacements would pass a value comparison
    while having rewritten history.
    """
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")
    before = snapshot(case_id)
    assert before, "the fixture case must have results to protect"

    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    assert snapshot(case_id) == before


def test_a_failed_run_promotes_nothing_to_current(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")

    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    failed = next(r for r in _runs(db_session, case_id) if r.status == AssessmentRunStatus.FAILED)
    assert (
        db_session.scalars(
            select(AssessmentResult).where(AssessmentResult.assessment_run_id == failed.id)
        ).all()
        == []
    ), "the failed run wrote results that survived the rollback"

    # The travel change staled four results; they must still be STALE, not refreshed.
    stale = db_session.scalars(
        select(AssessmentResult).where(
            AssessmentResult.case_id == uuid.UUID(case_id),
            AssessmentResult.currency == Currency.STALE.value,
        )
    ).all()
    assert len(stale) == 4


# --- 2. the failure is durable and legible ---------------------------------


def test_the_failure_is_recorded_as_a_failed_run_with_a_code(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    case_id = _assessed_case(api)
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    runs = _runs(db_session, case_id)
    assert [r.status for r in runs] == [
        AssessmentRunStatus.COMPLETED.value,
        AssessmentRunStatus.FAILED.value,
    ], "the failed run must be recorded alongside the successful one, not instead of it"
    assert runs[-1].failure_summary == RecalculationFailureCode.UNEXPECTED_ERROR.value
    assert runs[-1].completed_at is not None


def test_a_rule_configuration_failure_carries_its_own_code(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    """The two codes exist because they call for different responses: this one will fail
    identically on every retry, so it is worth telling apart from a transient."""
    case_id = _assessed_case(api)
    break_persistence(exc=assessments_service.RuleConfigurationMissing("no active rule version"))
    with pytest.raises(assessments_service.RuleConfigurationMissing):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    assert (
        _runs(db_session, case_id)[-1].failure_summary
        == RecalculationFailureCode.RULE_CONFIGURATION_INVALID.value
    )


def test_the_exception_text_is_never_persisted_anywhere(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    """`failure_summary` is `Text`, and `str(exc)` is the obvious thing to put in it.

    A driver error renders its statement's bound parameters, so an exception string is a
    direct route from a destination label into a column nothing treats as case data (§11).
    The canary is checked against every table the failure path writes, not only the one
    column, because the event payload and the audit entry are just as reachable.
    """
    case_id = _assessed_case(api)
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    for table in ("assessment_runs", "issues", "domain_events", "audit_entries", "outbox_events"):
        mapped = Base.metadata.tables[table]
        rows = db_session.execute(select(*mapped.c)).all()
        rendered = " ".join(str(value) for row in rows for value in row)
        assert PII_MARKER not in rendered, f"the exception text reached {table}"


def test_the_failure_opens_a_processing_failure_issue_that_outlives_the_request(
    api: Api, break_persistence: Callable[..., None]
) -> None:
    """The point of the whole slice: the record survives the reload that erases a banner.

    Read back through the API, not the session, because that is the path the screen takes.
    """
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    queue = _queue(api, case_id)
    failures = [
        issue
        for group in queue["groups"]
        for issue in group["issues"]
        if issue["issue_type"] == IssueType.PROCESSING_FAILURE.value
    ]
    assert len(failures) == 1
    failure = failures[0]
    assert failure["status"] == IssueStatus.OPEN.value
    assert failure["severity"] == "ACTION_REQUIRED"
    # Never dismissible: setting it aside would leave the user looking at unrefreshed
    # figures with nothing on screen saying so.
    assert failure["dismissibility"] == "NOT_DISMISSIBLE"
    assert failure["affected_object_type"] == "Case"
    assert "did not finish" in (failure["body"] or "")
    assert "still the ones worked out before your last edit" in (failure["body"] or "")


def test_the_failure_sorts_above_the_stale_items_it_explains(
    api: Api, break_persistence: Callable[..., None]
) -> None:
    """It opens last, because it is a consequence of trying to clear them. Ordering by time
    alone would put the cause below its own effects."""
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    # Both types are cleared by the same recalculation, so they share one action group —
    # named for that action rather than for their severity (see `TYPE_ACTION_GROUPS`).
    group = next(
        g for g in _queue(api, case_id)["groups"] if g["action_group"] == "RECHECK_CONCLUSIONS"
    )
    assert group["issues"][0]["issue_type"] == IssueType.PROCESSING_FAILURE.value
    assert {i["issue_type"] for i in group["issues"][1:]} == {IssueType.STALE_ASSESSMENT.value}


def test_a_second_failure_does_not_resolve_the_first(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    """Keyed on the case, not on the failed run.

    Keying on the run would resolve the first failure's issue and open a second on every
    retry — writing a `SYSTEM_AUTO_RESOLVED` row for a failure that nothing resolved, while
    the case is still in exactly the state the first issue described.
    """
    case_id = _assessed_case(api)
    break_persistence()
    for _ in range(2):
        with pytest.raises(RuntimeError):
            api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    issues = _issues(db_session, case_id, IssueType.PROCESSING_FAILURE)
    assert len(issues) == 1
    assert issues[0].status == IssueStatus.OPEN.value
    assert issues[0].reopened_at is None
    resolutions = db_session.scalars(
        select(IssueResolution).where(IssueResolution.issue_id == issues[0].id)
    ).all()
    assert resolutions == [], "a retry that failed again recorded a resolution"
    # Both attempts are recorded, so "how many times has this failed?" is answerable.
    assert sum(1 for r in _runs(db_session, case_id) if r.status == "FAILED") == 2


def test_the_next_successful_run_resolves_it_through_the_ordinary_diff(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    """No special-case cleanup. The issue is derived from "the latest run failed", so a
    later successful run stops the derivation naming it and the reconciler resolves it the
    same way it resolves everything else."""
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")
    break_persistence(after=0)
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    break_persistence(after=1_000)  # the retry succeeds
    assert api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate").status_code == 200

    queue = _queue(api, case_id)
    assert queue["open_count"] == 0
    settled = [i for i in queue["history"] if i["issue_type"] == IssueType.PROCESSING_FAILURE.value]
    assert len(settled) == 1
    assert settled[0]["status"] == IssueStatus.RESOLVED.value
    assert settled[0]["resolutions"][0]["resolution_type"] == "SYSTEM_AUTO_RESOLVED"

    db_session.rollback()
    assert _issues(db_session, case_id, IssueType.PROCESSING_FAILURE)[0].resolved_at is not None


def test_a_precondition_failure_records_nothing(api: Api, db_session: Session) -> None:
    """A case with no application date has not suffered a processing failure. The request
    was wrong and the case is fine; a FAILED run would put an item in the queue that no
    retry could ever clear."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api("user_a").put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    response = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert response.status_code == 409
    assert response.json()["code"] == "CASE_NOT_ASSESSABLE"

    db_session.rollback()
    assert _runs(db_session, case_id) == []
    assert _issues(db_session, case_id, IssueType.PROCESSING_FAILURE) == []


def test_latest_is_decided_by_when_a_run_finished_not_by_its_transaction(
    api: Api, db_session: Session
) -> None:
    """A defect this slice hit, pinned directly rather than only through the flow.

    `started_at` carries a `server_default` of `now()`, which in Postgres is the
    *transaction* timestamp. The recovery write opens its own connection, so its
    transaction can begin **after** one that later inserts the successful retry — the
    failure then reads as the newer run and the queue keeps showing a processing failure
    the user already cleared. The rows below reproduce exactly that inversion.
    """
    case_id = uuid.UUID(_assessed_case(api))
    db_session.rollback()

    earlier, later = datetime(2027, 1, 1, 9, 0, tzinfo=UTC), datetime(2027, 1, 1, 9, 5, tzinfo=UTC)
    failed = AssessmentRun.start(
        case_id=case_id,
        trigger_type=AssessmentTriggerType.USER_REQUESTED,
        mode=AssessmentMode.TRUSTED,
        initiated_by="user_a",
    )
    failed.fail(code=RecalculationFailureCode.UNEXPECTED_ERROR, at=later)
    # The retry *finished* later but its transaction opened first — the inversion.
    retry = AssessmentRun.start(
        case_id=case_id,
        trigger_type=AssessmentTriggerType.USER_REQUESTED,
        mode=AssessmentMode.TRUSTED,
        initiated_by="user_a",
    )
    retry.complete(at=datetime(2027, 1, 1, 9, 10, tzinfo=UTC))
    failed.started_at, retry.started_at = later, earlier
    db_session.add_all([failed, retry])
    db_session.flush()

    latest = AssessmentRepository.get_latest_finished_run(db_session, case_id)
    assert latest is not None
    assert latest.id == retry.id
    assert latest.status == AssessmentRunStatus.COMPLETED.value


def test_a_run_that_never_finished_is_not_treated_as_the_latest_word(
    api: Api, db_session: Session
) -> None:
    """A RUNNING row is a process that died mid-flight. It is not evidence of failure, and
    letting it win would suppress the outcome of the last run that actually finished."""
    case_id = uuid.UUID(_assessed_case(api))
    db_session.rollback()

    orphan = AssessmentRun.start(
        case_id=case_id,
        trigger_type=AssessmentTriggerType.USER_REQUESTED,
        mode=AssessmentMode.TRUSTED,
        initiated_by="user_a",
    )
    db_session.add(orphan)
    db_session.flush()

    latest = AssessmentRepository.get_latest_finished_run(db_session, case_id)
    assert latest is not None and latest.id != orphan.id
    assert latest.status == AssessmentRunStatus.COMPLETED.value


def test_a_concurrency_conflict_records_no_failure(
    api: Api, db_session: Session, break_persistence: Callable[..., None]
) -> None:
    """Another writer holds the results this run would have written, so the recalculation
    it performed stands and a retry is the documented response to a 409.

    Pinned separately from the precondition case: deleting the `except DomainError` clause
    fails only the not-assessable test, which would leave this half of the rule resting on
    a comment.
    """
    case_id = _assessed_case(api)
    break_persistence(exc=ConcurrencyConflict())

    response = api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert response.status_code == 409

    db_session.rollback()
    assert [r.status for r in _runs(db_session, case_id)] == [AssessmentRunStatus.COMPLETED.value]
    assert _issues(db_session, case_id, IssueType.PROCESSING_FAILURE) == []


# --- 3. the recovery never eats the original error -------------------------


def test_a_broken_recovery_write_does_not_mask_the_original_error(
    api: Api,
    monkeypatch: pytest.MonkeyPatch,
    break_persistence: Callable[..., None],
    snapshot: Callable[[str], dict[uuid.UUID, tuple[str, str]]],
) -> None:
    """The failure mode that guarantees the recovery also fails — a dead connection — is
    the one where the original error matters most. If the recovery raised, the engineer
    would be shown its exception and lose the cause on the way out.

    The durable record is an improvement on the safe state, not a precondition for it: the
    results are already STALE and nothing was promoted whether or not this write lands.
    """
    case_id = _assessed_case(api)
    _add_trip(api, case_id, "2023-06-01", "2023-07-02")
    before = snapshot(case_id)

    def broken() -> Any:
        raise OSError("the recovery session is unreachable too")

    monkeypatch.setattr(assessments_service, "get_sessionmaker", broken)
    break_persistence()

    with pytest.raises(RuntimeError, match="evaluator exploded"):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert snapshot(case_id) == before, "the safe state must hold without the durable record"


def test_the_recovery_enters_the_rls_tenant_context(
    api: Api,
    monkeypatch: pytest.MonkeyPatch,
    break_persistence: Callable[..., None],
    rls_sessionmaker: Callable[[], Session],
) -> None:
    """The recovery's `set_tenant` call, pinned by a connection that can actually refuse.

    The suite's ordinary connection is `citizenship`, a superuser, and a superuser
    bypasses RLS even under FORCE. So the recovery's write lands whether or not the tenant
    was set: deleting the line used to leave the whole suite green while every failure
    record in a deployed environment would be silently rejected by policy — silently,
    because `_record_failed_run` swallows and logs.

    This test used to compensate by having the fake session `SET ROLE app_rls` itself,
    which meant the test simulated the very enforcement it was checking; deleting both
    lines together still passed. It now points the recovery at `app_test_login`, a real
    non-superuser login role (`tests/conftest.py`), so nothing here simulates anything and
    the policy is what decides. Deleting `set_tenant` from `_record_failed_run` turns this
    red on its own.

    The recovery opens and closes its own session, so `rls_sessionmaker` is handed over
    whole — and because that session never commits before its single insert, it does not
    meet the mid-request-commit defect in `tests/security/test_rls_login_role.py`.
    """
    monkeypatch.setattr(assessments_service, "get_sessionmaker", lambda: rls_sessionmaker)
    real_sessionmaker = get_sessionmaker()

    case_id = _assessed_case(api)
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    with real_sessionmaker() as fresh:
        set_tenant(fresh, "user_a")
        assert _runs(fresh, case_id)[-1].status == AssessmentRunStatus.FAILED.value
        assert len(_issues(fresh, case_id, IssueType.PROCESSING_FAILURE)) == 1


def test_the_failed_transaction_is_discarded_before_the_recovery_opens(
    api: Api, monkeypatch: pytest.MonkeyPatch, break_persistence: Callable[..., None]
) -> None:
    """`_abandon` must run *before* `_record_failed_run`, and the coupling is real: the
    recovery's FK check on `assessment_runs -> cases` needs `FOR KEY SHARE` on the case
    row, which the un-rolled-back transaction still holds `FOR UPDATE`.

    Removing the rollback therefore does not fail the suite — it **deadlocks** it, so the
    regression arrives as an unbounded CI job rather than a red assertion. This test names
    the defect in one line when it is run, and skips the real recovery when the rollback is
    missing so it cannot hang itself. It does not rescue the rest of the file: every other
    test here still blocks under that mutation. A global pytest timeout would, and needs a
    dependency this repo has not agreed to add.
    """
    observed: dict[str, object] = {}
    original = assessments_service._record_failed_run
    request_session: dict[str, Session | None] = {"session": None}

    real_recalculate = assessments_service._run_trusted_assessment

    def capture_session(session: Session, **kwargs: Any) -> Any:
        request_session["session"] = session
        return real_recalculate(session, **kwargs)

    def spy(**kwargs: Any) -> None:
        captured = request_session["session"]
        assert isinstance(captured, Session)
        still_open = captured.in_transaction()
        observed["in_transaction"] = still_open
        # Deliberately skip the real recovery when the rollback is missing. Calling it
        # would block on the case-row lock the failed transaction still holds, and the
        # whole point of this test is to turn that hang into an assertion.
        if not still_open:
            original(**kwargs)

    monkeypatch.setattr(assessments_service, "_run_trusted_assessment", capture_session)
    monkeypatch.setattr(assessments_service, "_record_failed_run", spy)

    case_id = _assessed_case(api)
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    assert observed["in_transaction"] is False, (
        "the failed transaction was still open when the recovery ran; it holds FOR UPDATE "
        "on the case row and the recovery's FK check will block on it forever"
    )


def test_the_failure_is_dated_when_it_happened_not_when_the_recovery_opened(
    api: Api,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    break_persistence: Callable[..., None],
) -> None:
    """Reading the clock inside the recovery session dates the failure after anything that
    succeeded while it waited for a connection.

    `_abandon` releases the case lock one line earlier, so a concurrent recalculation can
    complete and commit in that gap — and a later-dated failure would then sort after it
    and raise a processing failure on a case whose every result is CURRENT. The delay is
    simulated here; in production it is a pooled checkout, which can block for the full
    pool timeout precisely when the pool is what broke.
    """
    case_id = _assessed_case(api)
    break_persistence()

    real_sessionmaker = get_sessionmaker()
    already_raced = {"done": False}

    def slow_sessionmaker() -> Callable[[], Session]:
        def open_session() -> Session:
            # Stand in for a successful concurrent run committing during the checkout.
            if not already_raced["done"]:
                with real_sessionmaker() as other:
                    set_tenant(other, "user_a")
                    winner = AssessmentRun.start(
                        case_id=uuid.UUID(case_id),
                        trigger_type=AssessmentTriggerType.USER_REQUESTED,
                        mode=AssessmentMode.TRUSTED,
                        initiated_by="user_a",
                    )
                    winner.complete(at=datetime.now(UTC))
                    other.add(winner)
                    other.commit()
                    already_raced["done"] = True
            return real_sessionmaker()

        return open_session

    monkeypatch.setattr(assessments_service, "get_sessionmaker", slow_sessionmaker)

    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    db_session.rollback()
    latest = AssessmentRepository.get_latest_finished_run(db_session, uuid.UUID(case_id))
    assert latest is not None
    assert latest.status == AssessmentRunStatus.COMPLETED.value, (
        "the failure was dated after a run that succeeded while the recovery waited for a "
        "connection, so the queue reports a processing failure on an up-to-date case"
    )


def test_the_recovery_runs_in_its_own_transaction(
    api: Api, break_persistence: Callable[..., None]
) -> None:
    """The failed transaction is rolled back by definition, so a record written inside it
    would vanish with everything else. This asserts the record is visible from a session
    that never saw the failed work."""
    case_id = _assessed_case(api)
    break_persistence()
    with pytest.raises(RuntimeError):
        api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    # A genuinely separate connection, not the request's rolled-back one.
    with get_sessionmaker()() as fresh:
        set_tenant(fresh, "user_a")
        assert _runs(fresh, case_id)[-1].status == AssessmentRunStatus.FAILED.value
        assert len(_issues(fresh, case_id, IssueType.PROCESSING_FAILURE)) == 1
