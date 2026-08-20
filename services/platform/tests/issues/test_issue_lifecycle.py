"""The issue lifecycle: open, auto-resolve, reopen, deduplicate (Domain §36.6, §47.4).

`STALE_ASSESSMENT` is the only type derived at this slice, and that is deliberate: it
exercises every transition in the aggregate with the smallest possible derivation, so a
failure here is a failure of the lifecycle rather than of one type's rules.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.issues.domain import Issue, IssueResolution, IssueStatus

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}


def _assessed_case(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    return case_id


def _add_trip(api: Api, user: str, case_id: str, dep: str, ret: str) -> None:
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


def _queue(api: Api, user: str, case_id: str) -> dict[str, Any]:
    payload: dict[str, Any] = api(user).get(f"/api/v1/cases/{case_id}/issues").json()
    return payload


def _open_keys(queue: dict[str, Any]) -> set[str]:
    return {
        issue["affected_object_id"]
        for group in queue["groups"]
        for issue in group["issues"]
    }


def test_an_assessed_case_with_nothing_wrong_has_an_empty_queue(api: Api) -> None:
    queue = _queue(api, "user_a", _assessed_case(api, "user_a"))
    assert queue["open_count"] == 0
    assert queue["groups"] == []
    assert queue["history"] == []


def test_a_travel_change_opens_one_issue_per_stale_requirement(api: Api) -> None:
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    queue = _queue(api, "user_a", case_id)
    # The four travel-dependent rules, not five: `qualifying_period` reads only the
    # application date, so it is neither stale nor an issue (ADR-0014).
    assert queue["open_count"] == 4
    assert "residence.qualifying_period" not in _open_keys(queue)
    assert _open_keys(queue) == {
        "residence.physical_presence_start_date",
        "residence.total_absences",
        "residence.final_year_absences",
        "residence.travel_consistency",
    }


def test_recalculation_auto_resolves_the_issues_it_makes_current(api: Api) -> None:
    """§41.3: stale issues resolve automatically. Not a special case in the recalculation
    path — the reconciler simply finds those causes gone."""
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")
    assert _queue(api, "user_a", case_id)["open_count"] == 4

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    queue = _queue(api, "user_a", case_id)
    assert queue["open_count"] == 0
    assert queue["groups"] == []
    # Resolved, not deleted (§36.6): the history says this was raised and cleared.
    assert len(queue["history"]) == 4
    assert {issue["status"] for issue in queue["history"]} == {"RESOLVED"}
    assert {
        resolution["resolution_type"]
        for issue in queue["history"]
        for resolution in issue["resolutions"]
    } == {"SYSTEM_AUTO_RESOLVED"}


def test_a_returning_cause_reopens_the_same_issue_and_keeps_its_history(api: Api) -> None:
    """§47.4: RESOLVED → cause returns → OPEN. The same row, so "has this come back?" is
    answerable rather than lost across two unrelated records."""
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")
    first = _queue(api, "user_a", case_id)
    first_ids = {i["id"] for g in first["groups"] for i in g["issues"]}

    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _queue(api, "user_a", case_id)["open_count"] == 0

    _add_trip(api, "user_a", case_id, "2024-02-01", "2024-03-01")

    reopened = _queue(api, "user_a", case_id)
    reopened_ids = {i["id"] for g in reopened["groups"] for i in g["issues"]}
    assert reopened_ids == first_ids, "a returning cause must reuse its issue, not fork a new one"

    for group in reopened["groups"]:
        for issue in group["issues"]:
            assert issue["status"] == "OPEN"
            assert issue["reopened_at"] is not None
            assert issue["has_recurred"] is True
            # The earlier auto-resolution is retained, not overwritten.
            assert any(r["resolution_type"] == "SYSTEM_AUTO_RESOLVED" for r in issue["resolutions"])


def test_reconciliation_is_idempotent(api: Api, db_session: Session) -> None:
    """Derivation is a pure function of durable state, so reconciling twice over unchanged
    state must be a no-op. If it were not, issues would flap open and closed across
    identical writes and the history would fill with noise."""
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    def _counts() -> tuple[int | None, int | None]:
        return (
            db_session.scalar(select(func.count()).select_from(Issue)),
            db_session.scalar(select(func.count()).select_from(IssueResolution)),
        )

    # The non-trivial case: reconcile repeatedly while four causes are still live. An
    # empty desired set diffed against an empty stored set would pass whatever the logic
    # does, so the causes must still be there.
    with_causes = _counts()
    assert with_causes[0] == 4

    for _ in range(3):
        _add_trip(api, "user_a", case_id, "2024-02-01", "2024-03-01")
    assert _counts() == with_causes, "reconciling live causes opened or resolved something"

    # And again once they are gone: resolving must happen once, not once per pass.
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    settled = _counts()
    assert settled[1] == 4, "expected exactly one resolution per issue"
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    assert _counts() == settled, "a no-change reconcile wrote rows"


def test_deduplication_is_enforced_by_the_database_not_only_the_service(
    api: Api, db_session: Session
) -> None:
    """§36.6. A partial unique index, so a concurrent double-reconcile raises rather than
    leaving the user a queue with two rows for one cause and no way to clear it."""
    from sqlalchemy.exc import IntegrityError

    from app.issues.domain import Dismissibility, IssueSeverity, IssueType

    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    existing = db_session.scalars(
        select(Issue).where(Issue.status == IssueStatus.OPEN.value)
    ).first()
    assert existing is not None

    db_session.add(
        Issue.open_new(
            case_id=existing.case_id,
            issue_type=IssueType.STALE_ASSESSMENT,
            severity=IssueSeverity.ACTION_REQUIRED,
            dismissibility=Dismissibility.NOT_DISMISSIBLE,
            deduplication_key=existing.deduplication_key,
            title_code="ISSUE_STALE_ASSESSMENT",
            affected_object_type="Requirement",
            affected_object_id=existing.affected_object_id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_stale_issue_cannot_be_dismissed(api: Api) -> None:
    """Dismissing it would leave a conclusion the product knows is out of date on screen
    with nothing saying so — false reassurance by consent."""
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")
    queue = _queue(api, "user_a", case_id)
    issue = queue["groups"][0]["issues"][0]
    assert issue["dismissibility"] == "NOT_DISMISSIBLE"

    response = api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")
    assert response.status_code == 409


def test_the_queue_is_case_scoped(api: Api) -> None:
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")
    assert api("user_b").get(f"/api/v1/cases/{case_id}/issues").status_code == 404


def test_an_issue_never_changes_a_conclusion(api: Api) -> None:
    """§36.6, and CLAUDE.md §2: an issue is a projection of assessment state, never an
    input to it. Opening four issues must leave every conclusion exactly as it was."""
    case_id = _assessed_case(api, "user_a")
    before = {
        r["requirement_key"]: r["conclusion"]
        for r in api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    }
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")
    assert _queue(api, "user_a", case_id)["open_count"] == 4

    after = {
        r["requirement_key"]: r["conclusion"]
        for r in api("user_a").get(f"/api/v1/cases/{case_id}/requirements").json()
    }
    assert after == before


def test_a_dismissed_issue_resolves_when_its_cause_goes_and_reopens_when_it_returns(
    api: Api, db_session: Session
) -> None:
    """The reopen hole, pinned.

    Dismissal is a judgement about *this episode* of a cause, not a standing waiver on the
    cause. So when the cause disappears a dismissed issue must leave the live set. If it
    stayed DISMISSED, reconciliation would find a live row when the cause returned, leave
    it alone, and tell the user nothing — a silent failure to reopen, which is the class of
    defect this milestone exists to close.

    No derived type is dismissible at this slice, so the DISMISSED state is set directly
    rather than through the API. The transition under test is the reconciler's, not the
    dismiss endpoint's.
    """
    case_id = _assessed_case(api, "user_a")
    _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    issue = db_session.scalars(
        select(Issue).where(Issue.affected_object_id == "residence.total_absences")
    ).one()
    original_id = issue.id
    issue.status = IssueStatus.DISMISSED.value
    db_session.flush()

    # The cause persists, so a reconcile must leave the dismissal standing.
    _add_trip(api, "user_a", case_id, "2024-06-01", "2024-06-10")
    db_session.refresh(issue)
    assert issue.status == IssueStatus.DISMISSED.value, "a live cause must not clear a dismissal"

    # Cause gone: the dismissal is spent, and the issue leaves the live set.
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")
    db_session.refresh(issue)
    assert issue.status == IssueStatus.RESOLVED.value
    assert issue.resolved_at is not None

    # Cause returns: a new episode on the same row, not silence.
    _add_trip(api, "user_a", case_id, "2025-01-01", "2025-01-20")
    db_session.refresh(issue)
    assert issue.id == original_id
    assert issue.status == IssueStatus.OPEN.value
    assert issue.reopened_at is not None


def test_the_queue_and_the_stale_marks_commit_together_or_not_at_all(
    api: Api, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§41.2, held by a test rather than by a comment.

    A stale conclusion and the issue announcing it must never disagree, so both are written
    on the input command's own unit of work. This was true by convention at four call sites
    and a reviewer showed the whole coupling could be deleted with the suite still green —
    moving reconciliation onto its own transaction changed nothing that failed. It now lives
    inside `invalidate_for_input_change`, and this test is what keeps it there.
    """
    from sqlalchemy import func

    from app.assessments.domain import AssessmentResult
    from app.requirements.domain import Currency

    case_id = _assessed_case(api, "user_a")

    def _stale_count() -> int | None:
        return db_session.scalar(
            select(func.count())
            .select_from(AssessmentResult)
            .where(AssessmentResult.currency == Currency.STALE.value)
        )

    assert _stale_count() == 0
    assert db_session.scalar(select(func.count()).select_from(Issue)) == 0

    # Fail after the results are staled and the issues derived, before the commit.
    import app.issues.service as issues

    real_reconcile = issues.reconcile

    def _boom(*args: object, **kwargs: object) -> object:
        real_reconcile(*args, **kwargs)  # type: ignore[arg-type]
        raise RuntimeError("failed after reconciling, before commit")

    monkeypatch.setattr(issues, "reconcile", _boom)
    with pytest.raises(RuntimeError):
        _add_trip(api, "user_a", case_id, "2023-06-01", "2023-07-02")

    # In production the failed request's session closes uncommitted; the shared test
    # session models that with an explicit rollback.
    db_session.rollback()

    # Neither half survives. The dangerous asymmetry is stale-without-issue: conclusions
    # marked out of date while the queue says nothing needs attention.
    assert _stale_count() == 0
    assert db_session.scalar(select(func.count()).select_from(Issue)) == 0


def test_a_csv_import_populates_the_queue_like_any_other_travel_change(api: Api) -> None:
    """The seam a reviewer found unguarded: bulk import staled results and, before the
    reconcile moved into the invalidation service, left the queue empty — a case reading
    "nothing needs your attention" over conclusions the system knew were out of date."""
    case_id = _assessed_case(api, "user_a")
    csv = (
        "destination_label,departure_date,return_date,date_confidence\n"
        "Spain,2023-06-01,2023-07-02,EXACT\n"
    )
    response = api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/import",
        json={"content": csv},
    )
    assert response.status_code in (200, 201), response.text

    queue = _queue(api, "user_a", case_id)
    assert queue["open_count"] == 4, queue
