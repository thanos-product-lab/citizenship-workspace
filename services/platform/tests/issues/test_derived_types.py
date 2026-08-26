"""The issue types derived from assessment output (Domain §36.2), end to end.

`test_issue_lifecycle.py` proves the lifecycle on one type. This file proves each type's
own rule: what raises it, what severity it carries, whether it can be set aside, and that
it clears when its cause does.

The dismissal path is exercised here for the first time. Until this slice every derived
issue was NOT_DISMISSIBLE, so the endpoint and the reconciler's handling of a dismissed row
were guarded only by unit-level tests.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}
# Qualifying window for this date is 2022-04-16 → 2027-04-15.
APPLICATION_DATE = "2027-04-15"


def _case(api: Api, user: str = "user_a") -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": APPLICATION_DATE},
    )
    return case_id


def _trip(
    api: Api,
    case_id: str,
    dep: str,
    ret: str,
    *,
    label: str = "Spain",
    confidence: str = "EXACT",
    review: str = "CONFIRMED",
    user: str = "user_a",
) -> str:
    return str(
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": label,
                "departure_date": dep,
                "return_date": ret,
                "date_confidence": confidence,
                "review_state": review,
            },
        )
        .json()["id"]
    )


def _recalc(api: Api, case_id: str, user: str = "user_a") -> None:
    api(user).post(f"/api/v1/cases/{case_id}/assessments/recalculate")


def _queue(api: Api, case_id: str, user: str = "user_a") -> dict[str, Any]:
    payload: dict[str, Any] = api(user).get(f"/api/v1/cases/{case_id}/issues").json()
    return payload


def _open(queue: dict[str, Any]) -> list[dict[str, Any]]:
    return [issue for group in queue["groups"] for issue in group["issues"]]


def _of_type(queue: dict[str, Any], issue_type: str) -> list[dict[str, Any]]:
    return [i for i in _open(queue) if i["issue_type"] == issue_type]


# --- NEAR_THRESHOLD ----------------------------------------------------------


def test_a_near_threshold_conclusion_raises_a_review_issue(api: Api) -> None:
    case_id = _case(api)
    # 440 days across the window: inside the near-threshold band below 450.
    _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "NEAR_THRESHOLD")
    assert [i["affected_object_id"] for i in issues] == ["residence.total_absences"]
    assert issues[0]["severity"] == "REVIEW_REQUIRED"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "close to its threshold" in issues[0]["title"]


def test_the_near_threshold_issue_never_states_the_gap_as_headroom(api: Api) -> None:
    """The copy rule that governs the summary governs the queue too: "10 days remaining"
    is advice, and invites reading NEAR_THRESHOLD as a pass with room to spare."""
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "NEAR_THRESHOLD")[0]
    text = f"{issue['title']} {issue['body']} {issue['impact']}".lower()
    assert "remaining" not in text
    assert "left" not in text


def test_the_near_threshold_issue_clears_when_the_margin_widens(api: Api) -> None:
    case_id = _case(api)
    trip = _trip(api, case_id, "2023-01-01", "2024-03-15")
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "NEAR_THRESHOLD")

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").delete(
        f"/api/v1/cases/{case_id}/travel-records/{trip}",
        params={"expected_revision": record["revision"]},
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "NEAR_THRESHOLD") == []


# --- UNSUPPORTED_COMPLEXITY --------------------------------------------------


def test_an_absence_total_the_prototype_will_not_assess_raises_a_review_issue(
    api: Api,
) -> None:
    """UI/UX §10.2. Stopping is a successful outcome (CLAUDE.md §2.7), so it is surfaced
    rather than buried in a requirement nobody opens."""
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2025-01-01")  # far past every band
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNSUPPORTED_COMPLEXITY")
    assert issues, _queue(api, case_id)
    # REVIEW_REQUIRED, not BLOCKING: the bands escalate here because guidance normally
    # exercises discretion in this range, and nothing in the product is gated on it.
    assert issues[0]["severity"] == "REVIEW_REQUIRED"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "paused" in (issues[0]["body"] or "")
    # And it does not also raise a near-threshold item for the same requirement.
    affected = {i["affected_object_id"] for i in _of_type(_queue(api, case_id), "NEAR_THRESHOLD")}
    assert "residence.total_absences" not in affected


def test_an_escalated_issue_cannot_be_dismissed(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-01-01", "2025-01-01")
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "UNSUPPORTED_COMPLEXITY")[0]
    assert (
        api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss").status_code
        == 409
    )


# --- OVERLAPPING_TRAVEL ------------------------------------------------------


def test_overlapping_trips_raise_one_issue_per_record(api: Api) -> None:
    """One per record rather than one per pair: a pair has no single affected object to
    name (§36.1), and the user fixes the overlap by editing one of the two records."""
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Spain")
    _trip(api, case_id, "2023-06-15", "2023-07-20", label="Portugal")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")
    assert len(issues) == 2
    assert {i["severity"] for i in issues} == {"REVIEW_REQUIRED"}
    assert {i["affected_object_type"] for i in issues} == {"TravelRecord"}
    assert "Spain" in " ".join(i["title"] for i in issues)


def test_the_overlap_issue_clears_when_the_records_stop_overlapping(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Spain")
    _trip(api, case_id, "2023-06-15", "2023-07-20", label="Portugal")
    _recalc(api, case_id)
    assert len(_of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")) == 2

    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    second = next(r for r in records if r["destination_label"] == "Portugal")
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{second['id']}",
        json={
            "destination_label": "Portugal",
            "departure_date": "2023-08-01",
            "return_date": "2023-08-20",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": second["revision"],
        },
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL") == []


# --- UNCERTAIN_TRAVEL_DATE ---------------------------------------------------


def test_an_uncertain_date_inside_the_window_needs_an_action_and_cannot_be_dismissed(
    api: Api,
) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(issues) == 1
    assert issues[0]["severity"] == "ACTION_REQUIRED"
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "Confirm the dates" in issues[0]["title"]


def test_an_uncertain_date_outside_the_window_is_information_the_user_may_set_aside(
    api: Api,
) -> None:
    """The window judgement is the evaluator's, read from its limitation — this module
    never recomputes it (RULES_SPEC §7.8)."""
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(issues) == 1
    assert issues[0]["severity"] == "INFORMATION"
    assert issues[0]["dismissibility"] == "DISMISSIBLE"
    assert issues[0]["action_group"] == "FOR_YOUR_AWARENESS"


def test_an_uncertain_trip_keeps_its_issue_when_edited_but_still_uncertain(api: Api) -> None:
    """Identity is the record, not the version. Editing a trip mints a new version; if the
    issue were keyed on that, correcting a date without resolving the uncertainty would
    close one issue and open another, which reads as progress where there is none."""
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)
    before = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Greece",
            "departure_date": "2023-06-02",
            "return_date": "2023-07-01",
            "date_confidence": "ESTIMATED",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    after = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    assert after["id"] == before["id"]
    assert after["reopened_at"] is None, "the issue should never have closed"


def test_confirming_the_dates_resolves_the_issue(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")

    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Greece",
            "departure_date": "2023-06-01",
            "return_date": "2023-07-01",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE") == []


# --- dismissal, end to end ---------------------------------------------------


def test_dismissing_hides_an_issue_without_deleting_it(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]

    response = api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")
    assert response.status_code == 200
    assert response.json()["status"] == "DISMISSED"

    queue = _queue(api, case_id)
    assert _of_type(queue, "UNCERTAIN_TRAVEL_DATE") == []
    dismissed = [i for i in queue["history"] if i["id"] == issue["id"]]
    assert len(dismissed) == 1
    assert dismissed[0]["status"] == "DISMISSED"
    assert [r["resolution_type"] for r in dismissed[0]["resolutions"]] == ["USER_DISMISSED"]


def test_a_dismissed_issue_stays_dismissed_while_its_cause_persists(api: Api) -> None:
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")

    # Another write reconciles. The cause is still there and the user has decided about it.
    _trip(api, case_id, "2024-02-01", "2024-03-01", label="Italy")
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE") == []
    assert _queue(api, case_id)["open_count"] == 0


def test_a_dismissed_issue_reopens_when_its_cause_goes_and_returns(api: Api) -> None:
    """Dismissal is a judgement about this episode, not a standing waiver on the cause.
    Now reachable through the API, where before it could only be driven directly."""
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")

    # Cause gone: the dismissal is spent and the issue leaves the live set.
    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Japan",
            "departure_date": "2021-01-10",
            "return_date": "2021-02-10",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)
    settled = [i for i in _queue(api, case_id)["history"] if i["id"] == issue["id"]]
    assert settled and settled[0]["status"] == "RESOLVED"

    # Cause returns: a new episode on the same row, not silence.
    record = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()[0]
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{record['id']}",
        json={
            "destination_label": "Japan",
            "departure_date": "2021-01-10",
            "return_date": "2021-02-10",
            "date_confidence": "ESTIMATED",
            "review_state": "CONFIRMED",
            "expected_revision": record["revision"],
        },
    )
    _recalc(api, case_id)

    reopened = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(reopened) == 1
    assert reopened[0]["id"] == issue["id"]
    assert reopened[0]["has_recurred"] is True
    assert [r["resolution_type"] for r in reopened[0]["resolutions"]] == [
        "SYSTEM_AUTO_RESOLVED",
        "USER_DISMISSED",
    ]


# --- the two defects a reviewer reproduced -----------------------------------


def test_an_issue_reshapes_when_its_cause_changes_shape(api: Api) -> None:
    """A live issue's severity, dismissibility and wording are reconciled, not frozen at
    open time.

    `UNCERTAIN_TRAVEL_DATE` is the one type whose shape varies under a fixed deduplication
    key. Freeze it and the queue keeps saying "this trip falls outside your qualifying
    period, so it does not affect any figure" — with a Dismiss button beside it — about a
    date that is now holding a figure back.
    """
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    before = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    assert before["dismissibility"] == "DISMISSIBLE"

    # Move the application date so the same trip now sits inside the qualifying period.
    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2025-06-01", "expected_revision": current["revision"]},
    )
    _recalc(api, case_id)

    after = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    assert after["id"] == before["id"], "the same cause should keep its issue"
    assert after["severity"] == "ACTION_REQUIRED"
    assert after["dismissibility"] == "NOT_DISMISSIBLE"
    assert "outside your qualifying period" not in (after["body"] or "")


def test_a_dismissal_does_not_survive_the_issue_becoming_serious(api: Api) -> None:
    """The user set the issue aside *as it was presented*. Presented differently, it is a
    different judgement, and the dismissal is spent."""
    case_id = _case(api)
    _trip(api, case_id, "2021-01-10", "2021-02-10", label="Japan", confidence="ESTIMATED")
    _recalc(api, case_id)
    issue = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{issue['id']}/dismiss")
    assert _queue(api, case_id)["open_count"] == 0

    current = api("user_a").get(f"/api/v1/cases/{case_id}/application-dates").json()
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2025-06-01", "expected_revision": current["revision"]},
    )
    _recalc(api, case_id)

    reopened = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(reopened) == 1
    assert reopened[0]["id"] == issue["id"]
    assert reopened[0]["dismissibility"] == "NOT_DISMISSIBLE"


def test_a_stale_result_does_not_make_an_overlap_look_resolved(api: Api) -> None:
    """A limitation names the record *versions* the evaluator read. Match those against
    current versions only and a stale result drops them all — so an overlap that still
    exists reads as fixed, and the queue records a resolution that never happened."""
    case_id = _case(api)
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Spain")
    _trip(api, case_id, "2023-06-15", "2023-07-20", label="Portugal")
    _recalc(api, case_id)
    assert len(_of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")) == 2

    # Edit one trip so it still overlaps, leaving the result stale.
    records = api("user_a").get(f"/api/v1/cases/{case_id}/travel-records").json()
    portugal = next(r for r in records if r["destination_label"] == "Portugal")
    api("user_a").patch(
        f"/api/v1/cases/{case_id}/travel-records/{portugal['id']}",
        json={
            "destination_label": "Portugal",
            "departure_date": "2023-06-15",
            "return_date": "2023-07-21",
            "date_confidence": "EXACT",
            "review_state": "CONFIRMED",
            "expected_revision": portugal["revision"],
        },
    )

    still_open = _of_type(_queue(api, case_id), "OVERLAPPING_TRAVEL")
    assert len(still_open) == 2, "the trips still overlap; the issues must not self-resolve"


def test_a_trip_the_evaluator_has_not_seen_is_never_called_harmless(api: Api) -> None:
    """A record added since the last assessment is absent from the limitation for the same
    reason a genuinely out-of-window one is. Only provenance separates them: absent *and*
    judged means out of scope; absent and unjudged means unknown, which takes the stronger
    shape rather than offering a Dismiss button."""
    case_id = _case(api)
    _trip(api, case_id, "2024-02-01", "2024-03-01", label="Italy")
    _recalc(api, case_id)

    # Added after the run: clearly inside the window, and unjudged.
    _trip(api, case_id, "2023-06-01", "2023-07-01", label="Greece", confidence="ESTIMATED")

    issues = _of_type(_queue(api, case_id), "UNCERTAIN_TRAVEL_DATE")
    assert len(issues) == 1
    assert issues[0]["dismissibility"] == "NOT_DISMISSIBLE"
    assert "outside your qualifying period" not in (issues[0]["body"] or "")


def test_the_narrow_margin_issue_names_the_inputs_that_move_it(api: Api) -> None:
    """The holding period reads the grant date and the application date. It has no bands and
    a travel record cannot shift it, so it must not borrow the absence copy."""
    case_id = str(api("user_a").post("/api/v1/cases", json={"title": "Margin"}).json()["id"])
    api("user_a").put(
        f"/api/v1/cases/{case_id}/route-profile",
        json={**SUPPORTED_ANSWERS, "status_granted_on": "2026-06-01"},
    )
    api("user_a").post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api("user_a").post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-06-05"},
    )
    _recalc(api, case_id)

    issues = [
        i
        for i in _of_type(_queue(api, case_id), "NEAR_THRESHOLD")
        if i["affected_object_id"] == "status.holding_period"
    ]
    assert issues, _queue(api, case_id)
    text = f"{issues[0]['body']} {issues[0]['impact']}"
    assert "travel records" not in text
    assert "grant date" in text


# --- MISSING_EVIDENCE --------------------------------------------------------


def _upload(api: Api, case_id: str, *, user: str = "user_a", name: str = "A booking") -> str:
    """Put one real document in the case, through the two-call upload path."""
    from app.core.storage import InMemoryStorage, get_storage
    from tests.evidence.conftest import fixture_bytes

    content = fixture_bytes("travel-booking.pdf")
    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), content)
    return str(
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "upload_token": grant["upload_token"],
                "category": "TRAVEL_SUPPORT",
                "display_name": name,
                "original_filename": "booking.pdf",
            },
        )
        .json()["id"]
    )


def _attach(api: Api, case_id: str, trip_id: str, item_id: str, *, user: str = "user_a") -> None:
    api(user).post(
        f"/api/v1/cases/{case_id}/travel-records/{trip_id}/evidence",
        json={"evidence_item_id": item_id},
    )


def test_a_case_with_no_documents_at_all_raises_no_evidence_issues(api: Api) -> None:
    """The suppression gate, and the reason it exists.

    Twelve trips and nothing uploaded would otherwise open twelve identical items, burying
    the one issue that needs a decision. Before the user has uploaded anything, "no
    documents have been provided" is one fact about the case rather than twelve problems
    with it.

    Nothing is hidden: the limitation is still on the requirement, and the travel history
    shows each trip's support state in its own column. What is suppressed is the
    *duplication of that into a queue* whose value is that everything in it is actionable.
    """
    case_id = _case(api)
    for month in (5, 6, 7):
        _trip(api, case_id, f"2023-0{month}-01", f"2023-0{month}-10", label=f"Trip {month}")
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "MISSING_EVIDENCE") == []


def test_the_other_trips_appear_once_the_first_document_is_uploaded(api: Api) -> None:
    """The other side of the gate. Once a document exists the user is evidencing the case,
    and the trips they have not got to yet are exactly the gaps worth listing.

    Note the gate turns on *uploading*, not on *attaching*: this document is attached to
    nothing, and all three trips are listed. Keying on attachment would make the first
    attach open issues for every other trip, which reads as being punished for progress.
    """
    case_id = _case(api)
    for month in (5, 6, 7):
        _trip(api, case_id, f"2023-0{month}-01", f"2023-0{month}-10", label=f"Trip {month}")
    _upload(api, case_id)
    _recalc(api, case_id)

    issues = _of_type(_queue(api, case_id), "MISSING_EVIDENCE")
    assert len(issues) == 3


def test_the_gaps_appear_when_the_document_is_uploaded_not_when_one_is_attached(
    api: Api,
) -> None:
    """The gate's timing, which its own docstring got wrong until a review caught it.

    Uploading stales nothing, so it fired no invalidation and therefore no reconciliation:
    the gate flipped true with nothing to notice, and the coverage items first appeared at
    the next invalidating write — the first *attach*. That is exactly the behaviour the
    gate exists to avoid. A user attaches one booking and is handed an issue for every
    trip they have not got to yet, which reads as being punished for progress.

    `record_upload` now reconciles. It does not invalidate: a document arriving in the
    library changes no input any rule reads.
    """
    case_id = _case(api)
    for month in (5, 7):
        _trip(api, case_id, f"2023-0{month}-01", f"2023-0{month}-10", label=f"Trip {month}")
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "MISSING_EVIDENCE") == []

    # Uploading alone — nothing attached anywhere — must surface both gaps.
    _upload(api, case_id)

    assert len(_of_type(_queue(api, case_id), "MISSING_EVIDENCE")) == 2


def test_an_unevidenced_trip_is_information_the_user_may_set_aside(api: Api) -> None:
    """SYNTHETIC_DEMO_CASE §10: INFORMATION, dismissible. A trip with no booking is not a
    defect — people take trips they have no paperwork for, and no figure moves either
    way."""
    case_id = _case(api)
    _trip(api, case_id, "2023-05-01", "2023-05-10", label="Greece")
    _upload(api, case_id)
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "MISSING_EVIDENCE")[0]
    assert issue["severity"] == "INFORMATION"
    assert issue["dismissibility"] == "DISMISSIBLE"
    assert "Greece" in issue["title"]


def test_attaching_a_document_clears_that_trips_issue_and_no_other(api: Api) -> None:
    """The cause goes away, so the issue does — and only for the trip that got the
    document. Reconciliation resolves what the derivation stops naming."""
    case_id = _case(api)
    greece = _trip(api, case_id, "2023-05-01", "2023-05-10", label="Greece")
    _trip(api, case_id, "2023-07-01", "2023-07-10", label="Italy")
    item_id = _upload(api, case_id)
    _recalc(api, case_id)
    assert len(_of_type(_queue(api, case_id), "MISSING_EVIDENCE")) == 2

    _attach(api, case_id, greece, item_id)
    _recalc(api, case_id)

    remaining = _of_type(_queue(api, case_id), "MISSING_EVIDENCE")
    assert len(remaining) == 1
    assert "Italy" in remaining[0]["title"]


def test_detaching_the_document_brings_the_issue_back(api: Api) -> None:
    """The same cause returns, so the same row reopens rather than a second one opening —
    the deduplication key is the trip, which does not change."""
    case_id = _case(api)
    greece = _trip(api, case_id, "2023-05-01", "2023-05-10", label="Greece")
    item_id = _upload(api, case_id)
    _attach(api, case_id, greece, item_id)
    _recalc(api, case_id)
    assert _of_type(_queue(api, case_id), "MISSING_EVIDENCE") == []

    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{greece}/evidence/{item_id}")
    _recalc(api, case_id)

    reopened = _of_type(_queue(api, case_id), "MISSING_EVIDENCE")
    assert len(reopened) == 1
    assert "Greece" in reopened[0]["title"]


def test_an_unconfirmed_trip_is_never_asked_for_a_document(api: Api) -> None:
    """§7.8 says *confirmed* trip. A record the user is still deciding about should not be
    generating paperwork requests."""
    case_id = _case(api)
    _trip(api, case_id, "2023-05-01", "2023-05-10", label="Maybe", review="DRAFT")
    _upload(api, case_id)
    _recalc(api, case_id)

    assert _of_type(_queue(api, case_id), "MISSING_EVIDENCE") == []


def test_the_issue_never_tells_the_user_their_totals_are_affected(api: Api) -> None:
    """The copy carries the load here. Nothing has read the attached document and no
    figure depends on one, so the body must not imply the totals are provisional until
    paperwork arrives — that would be false, and false in the reassuring direction."""
    case_id = _case(api)
    _trip(api, case_id, "2023-05-01", "2023-05-10", label="Greece")
    _upload(api, case_id)
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "MISSING_EVIDENCE")[0]
    assert "does not change any figure" in issue["body"]
    assert "set this aside" in issue["impact"]


# --- DUPLICATE_TRAVEL_RECORD -------------------------------------------------


def test_a_trip_recorded_twice_is_reported_as_a_duplicate_not_an_overlap(api: Api) -> None:
    """§7.8's precedence rule, which is the whole point of the detection.

    Identical trips already overlapped — their absent-date sets are the same set — so this
    pair was reported as `OVERLAPPING_TRAVEL` before slice 4b. That is the less accurate
    word for it and points at the wrong fix: correct a date, when what the user needs to do
    is remove a row.
    """
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _recalc(api, case_id)

    queue = _queue(api, case_id)
    duplicates = _of_type(queue, "DUPLICATE_TRAVEL_RECORD")
    assert len(duplicates) == 2, "one per record, as overlaps are"
    assert _of_type(queue, "OVERLAPPING_TRAVEL") == []
    assert all("Greece" in issue["title"] for issue in duplicates)


def test_the_duplicate_issue_is_information_the_user_may_set_aside(api: Api) -> None:
    """No figure is wrong — totals are a union, so the second copy adds nothing — and two
    identical rows may conceivably be two real trips. The product proposes; §11.8 forbids
    it merging anything on its own."""
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _recalc(api, case_id)

    issue = _of_type(_queue(api, case_id), "DUPLICATE_TRAVEL_RECORD")[0]
    assert issue["severity"] == "INFORMATION"
    assert issue["dismissibility"] == "DISMISSIBLE"
    assert "counted once" in issue["body"]


def test_a_genuine_overlap_still_reports_as_an_overlap(api: Api) -> None:
    """The suppression is scoped to the duplicate pair, not to the case. A trip overlapping
    something *other* than its own duplicate must keep saying so."""
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _trip(api, case_id, "2024-07-01", "2024-08-01", label="Italy")
    _recalc(api, case_id)

    queue = _queue(api, case_id)
    assert len(_of_type(queue, "DUPLICATE_TRAVEL_RECORD")) == 2
    overlaps = _of_type(queue, "OVERLAPPING_TRAVEL")
    assert len(overlaps) == 1, "only Italy, which overlaps without being a duplicate"
    assert "Italy" in overlaps[0]["title"]


def test_removing_one_copy_clears_both_duplicate_issues(api: Api) -> None:
    """The cause goes away, so both items do — reconciliation resolves what the derivation
    stops naming. And the overlap does not reappear in its place, because there is nothing
    left to overlap."""
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    second = _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _recalc(api, case_id)
    assert len(_of_type(_queue(api, case_id), "DUPLICATE_TRAVEL_RECORD")) == 2

    api("user_a").delete(f"/api/v1/cases/{case_id}/travel-records/{second}")
    _recalc(api, case_id)

    queue = _queue(api, case_id)
    assert _of_type(queue, "DUPLICATE_TRAVEL_RECORD") == []
    assert _of_type(queue, "OVERLAPPING_TRAVEL") == []


def test_dismissing_one_duplicate_leaves_the_other_open(api: Api) -> None:
    """Each record is its own cause with its own deduplication key. Setting aside the item
    on one row must not silently clear the other, which the user has not looked at."""
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _trip(api, case_id, "2024-06-05", "2024-07-15", label="Greece")
    _recalc(api, case_id)

    first = _of_type(_queue(api, case_id), "DUPLICATE_TRAVEL_RECORD")[0]
    api("user_a").post(f"/api/v1/cases/{case_id}/issues/{first['id']}/dismiss", json={})

    remaining = _of_type(_queue(api, case_id), "DUPLICATE_TRAVEL_RECORD")
    assert len(remaining) == 1
    assert remaining[0]["id"] != first["id"]


def test_identical_zero_day_trips_are_caught_though_they_never_overlapped(api: Api) -> None:
    """Depart D, return D+1 gives an empty absent-date set, and empty sets do not intersect.
    This pair was invisible to every detection before slice 4b."""
    case_id = _case(api)
    _trip(api, case_id, "2024-06-05", "2024-06-06", label="Greece")
    _trip(api, case_id, "2024-06-05", "2024-06-06", label="Greece")
    _recalc(api, case_id)

    queue = _queue(api, case_id)
    assert len(_of_type(queue, "DUPLICATE_TRAVEL_RECORD")) == 2
    assert _of_type(queue, "OVERLAPPING_TRAVEL") == []
