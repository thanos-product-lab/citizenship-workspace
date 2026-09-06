"""Reviewing a claim, through the API a client actually calls.

`test_boundary.py` asserts what cannot be done. This asserts what happens when someone
does the thing the product is for: reads a document, types what it says, and gets a
trusted fact with their name on it.

The blind-entry tests are the ones to read. Everything else in the milestone protects a
boundary; these are about whether the human on the other side of it was really asked.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.facts.domain import (
    ClaimStatus,
    ClaimType,
    ExtractedClaim,
    FactEvidenceLink,
    FactVersion,
    LinkAvailability,
)
from app.facts.values import ProposedValue, SourceMethod, ValueSchema
from tests.conftest import Api, ApiResponse

pytestmark = pytest.mark.integration


def _case_with_claim(
    api: Api,
    session: Session,
    *,
    claim_type: ClaimType = ClaimType.TRAVEL_DEPARTURE_DATE,
    raw: str = "4 May 2026",
    model_iso: str | None = "2026-05-04",
    user: str = "user_a",
) -> tuple[str, ExtractedClaim]:
    """A case holding one pending claim, built through the domain rather than the model.

    The extractor is exercised in `tests/evidence/`; here the question is what happens
    *after* a claim exists, and building one directly keeps these tests from depending on
    a provider to ask it.
    """
    from tests.security.conftest import SUPPORTED_ANSWERS

    case_id = str(api(user).post("/api/v1/cases", json={"title": "Review"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    chain = _evidence_chain(session, case_id=uuid.UUID(case_id), user=user)
    schema = ValueSchema.DATE_V1 if "date" in claim_type.value else ValueSchema.TEXT_V1
    claim = ExtractedClaim.propose(
        case_id=uuid.UUID(case_id),
        evidence_item_id=chain["item_id"],
        evidence_file_id=chain["file_id"],
        extraction_run_id=chain["run_id"],
        claim_type=claim_type,
        value=ProposedValue(schema=schema, raw=raw, model_iso=model_iso),
    )
    session.add(claim)
    session.flush()
    session.commit()
    return case_id, claim


def _second_journey(session: Session, claim: ExtractedClaim, *, raw: str) -> ExtractedClaim:
    """Another `travel.departure_date` from the same document, one journey along."""
    sibling = ExtractedClaim.propose(
        case_id=claim.case_id,
        evidence_item_id=claim.evidence_item_id,
        evidence_file_id=claim.evidence_file_id,
        extraction_run_id=claim.extraction_run_id,
        claim_type=ClaimType(claim.claim_type),
        journey_index=claim.journey_index + 1,
        value=ProposedValue(schema=ValueSchema.DATE_V1, raw=raw, model_iso=None),
    )
    session.add(sibling)
    session.flush()
    session.commit()
    return sibling


def _evidence_chain(session: Session, *, case_id: uuid.UUID, user: str) -> dict[str, uuid.UUID]:
    from app.ai.domain import Capability
    from app.ai.extraction_run import ExtractionRun, ExtractionRunStatus
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceCategory,
        EvidenceFile,
        EvidenceItem,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )

    item = EvidenceItem.uploaded(
        case_id=case_id,
        category=EvidenceCategory.TRAVEL_SUPPORT,
        display_name="Athens booking",
        created_by=user,
    )
    session.add(item)
    session.flush()
    file = EvidenceFile(
        evidence_item_id=item.id,
        storage_key=f"k/{uuid.uuid4()}",
        original_filename="booking.pdf",
        media_type="application/pdf",
        size_bytes=2048,
        checksum="c" * 64,
        version_number=1,
        uploaded_at=datetime.now(UTC),
    )
    session.add(file)
    session.flush()
    item.current_file_id = file.id
    processing = EvidenceProcessingRun(
        evidence_item_id=item.id,
        evidence_file_id=file.id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"review-{uuid.uuid4()}",
    )
    session.add(processing)
    session.flush()
    run = ExtractionRun.record(
        case_id=case_id,
        evidence_item_id=item.id,
        evidence_file_id=file.id,
        processing_run_id=processing.id,
        capability=Capability.TRAVEL_RECORD_EXTRACTOR.value,
        status=ExtractionRunStatus.SUCCEEDED,
        input_text="a booking",
        started_at=datetime.now(UTC),
        # No `classified_category`: migration 0031 scopes that column to
        # `DocumentClassifier`, because a category is what *that* capability concludes.
        # An extractor concludes a set of claims, in another table.
    )
    session.add(run)
    session.flush()
    return {"item_id": item.id, "file_id": file.id, "run_id": run.id}


def _review(api: Api, case_id: str, claim_id: uuid.UUID, **body: object) -> ApiResponse:
    return api("user_a").post(f"/api/v1/cases/{case_id}/claims/{claim_id}/review", json=body)


# --- blind entry --------------------------------------------------------------------


def test_the_queue_does_not_send_the_proposed_value_for_a_date(
    api: Api, db_session: Session
) -> None:
    """The blind-entry guarantee at the wire.

    A review screen that received the model's answer could render it beside the empty
    box a person is meant to fill from the document — which is a pre-filled confirm with
    extra steps. The value is not sent, so the client cannot show it even by accident.
    """
    case_id, _claim = _case_with_claim(api, db_session)

    items = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]

    (item,) = items
    assert item["requires_blind_entry"] is True
    assert item["proposed_value"] is None
    assert item["normalised_value"] is None
    assert "4 May 2026" not in str(items), "the proposal reached the client"


def test_typing_what_the_document_says_records_a_confirmation(
    api: Api, db_session: Session
) -> None:
    """The user reads 4 May and types it. Their value happens to match, so it is a
    CONFIRM — but nobody clicked a button labelled Confirm, which is the point."""
    case_id, claim = _case_with_claim(api, db_session)

    response = _review(api, case_id, claim.id, entered_value="4 May 2026")

    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "CONFIRM"
    assert body["review_mode"] == "BLIND_ENTRY"
    assert body["value"] == "2026-05-04"
    assert body["claim_status"] == "CONFIRMED"


def test_typing_something_else_records_a_correction_and_the_users_value_wins(
    api: Api, db_session: Session
) -> None:
    """The document says 11 May; the model proposed 4 May. The person's reading wins,
    and nobody had to notice a discrepancy and choose a different button."""
    case_id, claim = _case_with_claim(api, db_session)

    body = _review(api, case_id, claim.id, entered_value="11 May 2026").json()

    assert body["decision"] == "CORRECT"
    assert body["review_mode"] == "BLIND_ENTRY"
    assert body["value"] == "2026-05-11", "the model's value survived the user's"
    assert body["claim_status"] == "CORRECTED"


def test_a_correction_preserves_the_original_proposal(api: Api, db_session: Session) -> None:
    """CLAUDE.md §9. The claim still says what the model said; the correction lives on
    the decision. Without this, "what did the system propose before you fixed it" has no
    answer, and the evaluation signal in AI_EVALUATION_PLAN §15 is gone."""
    case_id, claim = _case_with_claim(api, db_session)
    _review(api, case_id, claim.id, entered_value="11 May 2026")

    db_session.expire_all()
    stored = db_session.get(ExtractedClaim, claim.id)
    assert stored is not None
    assert stored.proposed_raw == "4 May 2026", "the original proposal was overwritten"
    assert stored.proposed_iso == "2026-05-04"


def test_an_ambiguous_entry_is_refused_with_a_format_that_works(
    api: Api, db_session: Session
) -> None:
    """A person typing `03/04/2025` is exactly as ambiguous as a document containing it.

    Accepting it would let the interaction that exists to remove a guess quietly
    reintroduce one — so it is refused, and the message names a form that works rather
    than only saying no.

    **This assertion used to require a worked example**, `"11 May 2026" in detail` — and
    that is the demo booking's actual return date, so the test was insisting the server
    hand the user the proposal in an error message beside the empty box. The test
    encoded the defect. It now checks the message names an acceptable *shape*, and
    `test_no_message_on_the_blind_path_contains_a_worked_date` checks it carries no date
    at all.
    """
    case_id, claim = _case_with_claim(api, db_session)

    response = _review(api, case_id, claim.id, entered_value="03/04/2025")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UNREADABLE_ENTERED_VALUE"
    assert "YYYY-MM-DD" in body["detail"]
    assert "month" in body["detail"]


def test_a_high_risk_claim_can_still_be_rejected_outright(api: Api, db_session: Session) -> None:
    """ "This date is not in this document" is a real answer, and demanding a typed value
    for it would force someone to invent one."""
    case_id, claim = _case_with_claim(api, db_session)

    body = _review(
        api, case_id, claim.id, decision="REJECT", reason_code="VALUE_NOT_PRESENT"
    ).json()

    assert body["decision"] == "REJECT"
    assert body["claim_status"] == "REJECTED"
    assert body["fact_version_id"] is None, "a rejection created a fact"


# --- non-blind fields ---------------------------------------------------------------


def test_a_low_risk_field_keeps_its_proposed_value_and_a_stated_decision(
    api: Api, db_session: Session
) -> None:
    """Per-field friction is worth paying where a wrong value changes an assessment
    conclusion, and not where it does not. A booking reference is not a date."""
    case_id, claim = _case_with_claim(
        api,
        db_session,
        claim_type=ClaimType.TRAVEL_BOOKING_REFERENCE,
        raw="SKY-7P2QMN",
        model_iso=None,
    )

    items = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]
    assert items[0]["requires_blind_entry"] is False
    assert items[0]["proposed_value"] == "SKY-7P2QMN"

    body = _review(api, case_id, claim.id, decision="CONFIRM").json()
    assert body["review_mode"] == "PREFILLED"
    assert body["value"] == "SKY-7P2QMN"


# --- what a review leaves behind ------------------------------------------------------


def test_a_confirmation_creates_a_fact_with_its_provenance(api: Api, db_session: Session) -> None:
    """The chain RFC §14 describes, end to end: a fact that knows which decision
    authorised it, and which document it rests on."""
    case_id, claim = _case_with_claim(api, db_session)
    _review(api, case_id, claim.id, entered_value="4 May 2026")

    db_session.expire_all()
    version = db_session.execute(select(FactVersion)).scalar_one()
    assert version.source_method == SourceMethod.USER_CONFIRMED_AI_CLAIM.value
    assert version.claim_review_decision_id is not None
    assert version.version_number == 1

    link = db_session.execute(select(FactEvidenceLink)).scalar_one()
    assert link.fact_version_id == version.id
    assert link.claim_id == claim.id
    assert link.availability_status == LinkAvailability.AVAILABLE.value


def test_a_correction_records_that_the_user_corrected_it(api: Api, db_session: Session) -> None:
    """`USER_CORRECTED_AI_CLAIM`, not `USER_CONFIRMED_AI_CLAIM`. The two are told apart
    because §15 wants the corrected rate as an evaluation signal, and because a user
    asking "did I change this" deserves an answer."""
    case_id, claim = _case_with_claim(api, db_session)
    _review(api, case_id, claim.id, entered_value="11 May 2026")

    db_session.expire_all()
    version = db_session.execute(select(FactVersion)).scalar_one()
    assert version.source_method == SourceMethod.USER_CORRECTED_AI_CLAIM.value


def test_the_facts_endpoint_returns_facts_and_never_claims(api: Api, db_session: Session) -> None:
    """A trusted read has no shape a proposal could be serialised into."""
    case_id, claim = _case_with_claim(api, db_session)

    before = api("user_a").get(f"/api/v1/cases/{case_id}/facts").json()["items"]
    assert before == [], "a fact existed before anyone confirmed anything"

    _review(api, case_id, claim.id, entered_value="4 May 2026")

    (fact,) = api("user_a").get(f"/api/v1/cases/{case_id}/facts").json()["items"]
    assert fact["fact_type"] == "travel.departure_date"
    assert fact["value"] == "2026-05-04"
    assert fact["source_method"] == "USER_CONFIRMED_AI_CLAIM"


def test_a_claim_cannot_be_reviewed_twice(api: Api, db_session: Session) -> None:
    """Deciding twice would create a second fact from one proposal, or resurrect a
    rejection. RFC §25: concurrency must not silently overwrite review state."""
    case_id, claim = _case_with_claim(api, db_session)
    assert _review(api, case_id, claim.id, entered_value="4 May 2026").status_code == 201

    second = _review(api, case_id, claim.id, entered_value="11 May 2026")

    assert second.status_code == 409
    assert second.json()["code"] == "CLAIM_ALREADY_REVIEWED"
    db_session.expire_all()
    assert len(db_session.execute(select(FactVersion)).scalars().all()) == 1


def test_a_reviewed_claim_leaves_the_queue(api: Api, db_session: Session) -> None:
    case_id, claim = _case_with_claim(api, db_session)
    _review(api, case_id, claim.id, entered_value="4 May 2026")

    items = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]
    assert items == []


def test_another_users_claim_is_not_reviewable(api: Api, db_session: Session) -> None:
    """The ownership boundary. 404 rather than 403, so claim existence never leaks."""
    case_id, claim = _case_with_claim(api, db_session)

    response = api("user_b").post(
        f"/api/v1/cases/{case_id}/claims/{claim.id}/review",
        json={"entered_value": "4 May 2026"},
    )

    assert response.status_code == 404

    # The request under test left the shared session's tenant as `user_b`, so a refresh
    # here would find no row and report the claim deleted — a true statement about what
    # user_b can see, and not the question being asked.
    from app.shared.tenant import set_tenant

    set_tenant(db_session, "user_a")
    db_session.expire_all()
    stored = db_session.execute(
        select(ExtractedClaim).where(ExtractedClaim.id == claim.id)
    ).scalar_one()
    assert stored.status == ClaimStatus.PENDING_REVIEW.value, (
        "another user's review changed the claim"
    )


# --- what the reviews of slice 3a found ---------------------------------------------


def test_confirming_the_second_journey_does_not_supersede_the_first(
    api: Api, db_session: Session
) -> None:
    """A `CaseFact` is `(case_id, fact_type, scope_key)`, not `(case_id, fact_type)`.

    A two-leg booking proposes `travel.departure_date` twice — that is what
    `journey_index` is for — and `append_version` used to resolve both to one fact. The
    second confirmation appended a version and moved `current_version_id`, so the first
    journey's confirmed date stopped being the case's answer. Nothing failed: it looks
    exactly like a legitimate correction, which is why every test in this file passed
    while it was true. They all happened to build one claim.
    """
    from app.facts.domain import CaseFact

    case_id, first = _case_with_claim(api, db_session, raw="4 May 2026", model_iso="2026-05-04")
    second = _second_journey(db_session, first, raw="18 June 2026")

    _review(api, case_id, first.id, entered_value="4 May 2026")
    _review(api, case_id, second.id, entered_value="18 June 2026")

    db_session.expire_all()
    facts = db_session.execute(select(CaseFact)).scalars().all()
    assert len(facts) == 2, "two journeys resolved to one fact, so one overwrote the other"
    assert {f.scope_key for f in facts} == {
        f"{first.evidence_item_id}:0",
        f"{first.evidence_item_id}:1",
    }

    current = api("user_a").get(f"/api/v1/cases/{case_id}/facts").json()["items"]
    assert sorted(item["value"] for item in current) == ["2026-05-04", "2026-06-18"]
    # Both are version 1. A supersede chain here would mean the product had decided the
    # two journeys were the same thing.
    assert [item["version_number"] for item in current] == [1, 1]


def test_agreeing_with_a_model_guess_is_recorded_as_a_correction(
    api: Api, db_session: Session
) -> None:
    """The user's value wins, and so does the deterministic reading of the proposal.

    `09/04/2025` determines no date, so `normalise` returns None and the claim reaches
    review undecided — that much `test_boundary.py` already pins. What it did not cover
    is the comparison: `_resolve` also checked the entry against `model_iso`, the
    model's *guess*, and a user typing 9 April therefore had their fact stamped
    `USER_CONFIRMED_AI_CLAIM`.

    `source_method` is structural provenance (CLAUDE.md §2.5), so that is a guess
    deciding what the record says a human did. There was no reading of this proposal to
    agree with, so the honest answer is CORRECT: the value is the user's.
    """
    case_id, claim = _case_with_claim(api, db_session, raw="09/04/2025", model_iso="2025-04-09")
    assert claim.normalised_value is None, "the fixture is not ambiguous, so this proves nothing"

    body = _review(api, case_id, claim.id, entered_value="9 April 2025").json()

    assert body["decision"] == "CORRECT"
    db_session.expire_all()
    version = db_session.execute(select(FactVersion)).scalar_one()
    assert version.source_method == SourceMethod.USER_CORRECTED_AI_CLAIM.value
    assert version.raw_value == "2025-04-09", "the user's reading is still what is recorded"


def test_a_claim_cannot_be_reviewed_into_a_case_whose_deletion_was_requested(
    api: Api, db_session: Session
) -> None:
    """`require_case_access` filters DELETED, not DELETION_PENDING.

    So a review reached a case the purge is on its way to walk past, and wrote four rows
    — including a `FactVersion` holding a value, and a `FactEvidenceLink` marked
    AVAILABLE against a document being destroyed. Every other case-scoped write command
    in the codebase checks this; this one did not.

    The check is the visible half. The other half is the row lock taken before it, which
    is what stops a deletion committing *between* the check and the write — the failure
    `links.py` records from M7 and the reason a lifecycle check alone is not enough.
    """
    case_id, claim = _case_with_claim(api, db_session)
    assert api("user_a").delete(f"/api/v1/cases/{case_id}").status_code == 200

    refused = _review(api, case_id, claim.id, entered_value="4 May 2026")

    assert refused.status_code == 409
    db_session.expire_all()
    assert db_session.execute(select(FactVersion)).scalar_one_or_none() is None


def test_a_review_missing_what_its_decision_needs_is_refused_not_a_crash(
    api: Api, db_session: Session
) -> None:
    """422, not 500 — and the difference is a privacy one, not only a tidiness one.

    These were bare `ValueError`s, which FastAPI has no handler for. The frame they
    raise in holds `proposal`, the model's verbatim transcription of the document. The
    day Sentry is wired, `include_local_variables` defaults to true and a malformed
    request ships a traveller's name to a third party.
    """
    case_id, low_risk = _case_with_claim(
        api, db_session, claim_type=ClaimType.TRAVEL_ORIGIN, raw="London Gatwick", model_iso=None
    )
    # A non-blind field with no stated decision: nothing says what the user decided.
    refused = _review(api, case_id, low_risk.id)
    assert refused.status_code == 422
    assert refused.json()["code"] == "INCOMPLETE_REVIEW"

    case_id2, high_risk = _case_with_claim(api, db_session)
    # A blind field with a decision but nothing typed: the entry *is* the decision.
    refused2 = _review(api, case_id2, high_risk.id, decision="CONFIRM")
    assert refused2.status_code == 422
    assert refused2.json()["code"] == "INCOMPLETE_REVIEW"


# --- the split view's data ----------------------------------------------------------


def _document_claims(api: Api, case_id: str, evidence_item_id: uuid.UUID) -> list[Any]:
    body = api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{evidence_item_id}/claims")
    assert body.status_code == 200, body.text
    return list(body.json()["items"])


def test_a_documents_claims_include_the_ones_already_decided(api: Api, db_session: Session) -> None:
    """The queue answers "what is still open"; a document answers "what happened to it".

    `GET /claims` is `PENDING_REVIEW` only, deliberately — a decided claim in a queue
    invites a second decision. The split view needs the opposite: MVP §8.11 asks it to
    show confirmation history, and a screen that dropped a field the moment it was
    decided would leave the user looking at a shrinking list with no record of what they
    had just done.
    """
    case_id, first = _case_with_claim(api, db_session)
    second = _second_journey(db_session, first, raw="18 June 2026")

    _review(api, case_id, first.id, entered_value="4 May 2026")

    queue = api("user_a").get(f"/api/v1/cases/{case_id}/claims").json()["items"]
    assert [item["id"] for item in queue] == [str(second.id)], "a decided claim stayed in the queue"

    document = _document_claims(api, case_id, first.evidence_item_id)
    assert {item["id"] for item in document} == {str(first.id), str(second.id)}
    decided = next(item for item in document if item["id"] == str(first.id))
    assert decided["decision"]["decision"] == "CONFIRM"
    assert decided["decision"]["review_mode"] == "BLIND_ENTRY"
    assert decided["decision"]["value"] == "2026-05-04"
    assert decided["decision"]["reviewed_by"] == "user_a"
    still_open = next(item for item in document if item["id"] == str(second.id))
    assert still_open["decision"] is None


def test_a_proposal_is_withheld_until_it_is_decided_and_shown_afterwards(
    api: Api, db_session: Session
) -> None:
    """Both halves of the conditional reveal, in one test on purpose.

    Withholding is the blind-entry guarantee: a client that received the model's date
    could render it beside the empty box. Revealing afterwards is MVP §8.11's *"correcting
    a value preserves the original proposal"* — a promise nobody can see kept if the
    proposal is never returned at all.

    The two are one rule with a hinge, and splitting them across two tests is how a
    mutation that moves the hinge passes one of them. The reveal keys off
    `ClaimStatus.PENDING_REVIEW` — the same status `OPEN_STATUSES` gates the review
    command on — so the value becomes visible in exactly the instant the claim stops
    being reviewable.
    """
    case_id, claim = _case_with_claim(api, db_session, raw="10 May 2026", model_iso="2026-05-10")

    before = _document_claims(api, case_id, claim.evidence_item_id)
    assert before[0]["proposed_value"] is None
    assert before[0]["normalised_value"] is None
    assert "10 May 2026" not in str(before), "the proposal reached a screen that must not show it"

    # The correction the demo case turns on: the document says 11 May, the model read 10.
    _review(api, case_id, claim.id, entered_value="11 May 2026")

    after = _document_claims(api, case_id, claim.evidence_item_id)
    assert after[0]["proposed_value"] == "10 May 2026", (
        "the original proposal is gone, so a correction cannot be shown as one"
    )
    assert after[0]["decision"]["decision"] == "CORRECT"
    assert after[0]["decision"]["value"] == "2026-05-11", "the user's reading is what was recorded"


def test_a_low_risk_proposal_is_visible_throughout(api: Api, db_session: Session) -> None:
    """The reveal condition must not accidentally hide what was never hidden.

    `travel.origin` is pre-filled by design — the friction is spent where a wrong value
    changes a conclusion, and not where it does not (RFC §41.4). If the status check had
    been written as "hide until decided" rather than "hide *blind* fields until decided",
    every field would have gone blank and the pre-filled confirm would have had nothing
    to confirm.
    """
    case_id, claim = _case_with_claim(
        api, db_session, claim_type=ClaimType.TRAVEL_ORIGIN, raw="London Gatwick", model_iso=None
    )

    before = _document_claims(api, case_id, claim.evidence_item_id)
    assert before[0]["requires_blind_entry"] is False
    assert before[0]["proposed_value"] == "London Gatwick"

    _review(api, case_id, claim.id, decision="CONFIRM")

    after = _document_claims(api, case_id, claim.evidence_item_id)
    assert after[0]["proposed_value"] == "London Gatwick"


def test_a_deleted_documents_claims_are_a_404_not_an_empty_list(
    api: Api, db_session: Session
) -> None:
    """ "This document has no claims" and "this is not your document" are different
    answers, and a review screen that cannot tell them apart shows the wrong one — an
    empty panel reading as "nothing needs your decision" for a document that is gone."""
    case_id, claim = _case_with_claim(api, db_session)
    item_id = claim.evidence_item_id

    api("user_a").delete(f"/api/v1/cases/{case_id}/evidence/{item_id}")

    refused = api("user_a").get(f"/api/v1/cases/{case_id}/evidence/{item_id}/claims")
    assert refused.status_code == 404

    # And another user's document is the same 404, from the same raise site — a claim's
    # existence must not leak across the ownership boundary.
    other = api("user_b").get(f"/api/v1/cases/{case_id}/evidence/{item_id}/claims")
    assert other.status_code == 404


# --- the document stops asking ------------------------------------------------------


def _status(session: Session, evidence_item_id: uuid.UUID) -> str:
    from app.evidence.domain import EvidenceItem

    session.expire_all()
    item = session.get(EvidenceItem, evidence_item_id)
    assert item is not None
    return item.processing_status


def test_a_document_leaves_awaiting_confirmation_once_every_field_is_decided(
    api: Api, db_session: Session
) -> None:
    """The exit `AWAITING_CONFIRMATION` shipped without.

    Slice 3a gave the state a producer and nothing that clears it, so a document whose
    every field had been confirmed went on saying "needs your confirmation" — the library
    asserting outstanding work that no longer exists. Found by that slice's trust review.

    It settles on the *last* decision, not the first: a two-field document still needs
    the second answer, and moving early would drop it out of the queue with work left.
    """
    from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus

    case_id, first = _case_with_claim(api, db_session)
    second = _second_journey(db_session, first, raw="18 June 2026")
    item = db_session.get(EvidenceItem, first.evidence_item_id)
    assert item is not None
    item.processing_status = EvidenceProcessingStatus.AWAITING_CONFIRMATION.value
    db_session.commit()

    _review(api, case_id, first.id, entered_value="4 May 2026")
    assert _status(db_session, first.evidence_item_id) == "AWAITING_CONFIRMATION", (
        "the document settled while a field was still waiting"
    )

    _review(api, case_id, second.id, entered_value="18 June 2026")
    assert _status(db_session, first.evidence_item_id) == "COMPLETED"


def test_a_rejection_settles_the_document_as_surely_as_a_confirmation(
    api: Api, db_session: Session
) -> None:
    """What the state records is whether a person decided, not what they decided.

    Leaving the document waiting because its last field was rejected rather than
    confirmed would make the label depend on the *outcome* of a review — a document with
    nothing left to ask, still asking.
    """
    from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus

    case_id, claim = _case_with_claim(api, db_session)
    item = db_session.get(EvidenceItem, claim.evidence_item_id)
    assert item is not None
    item.processing_status = EvidenceProcessingStatus.AWAITING_CONFIRMATION.value
    db_session.commit()

    _review(api, case_id, claim.id, decision="REJECT", reason_code="VALUE_NOT_PRESENT")

    assert _status(db_session, claim.evidence_item_id) == "COMPLETED"


def test_a_document_that_could_not_be_read_is_never_marked_as_read(
    api: Api, db_session: Session
) -> None:
    """Mutation-table row 14, and the reason the state guard lives in `evidence`.

    A `FAILED` document has no claims, so nothing should ever call this for one — but
    "should never" is precisely how a document that could not be read ends up labelled
    "Text read", telling the user their file was fine when it was not. The refusal is a
    property of the seam rather than of every caller that might one day exist.
    """
    from app.evidence import service as evidence_service
    from app.evidence.domain import EvidenceItem, EvidenceProcessingStatus

    _case_id, claim = _case_with_claim(api, db_session)
    item = db_session.get(EvidenceItem, claim.evidence_item_id)
    assert item is not None

    for refused in (
        EvidenceProcessingStatus.FAILED,
        EvidenceProcessingStatus.UNSUPPORTED,
        EvidenceProcessingStatus.COMPLETED,
        EvidenceProcessingStatus.EXTRACTING_TEXT,
    ):
        item.processing_status = refused.value
        db_session.flush()

        moved = evidence_service.mark_review_settled(db_session, evidence_item_id=item.id)

        assert moved is False, f"a {refused.value} document was marked as reviewed"
        assert item.processing_status == refused.value


def test_no_message_on_the_blind_path_contains_a_worked_date(api: Api, db_session: Session) -> None:
    """Nothing the server says beside an empty date box may contain a date.

    A worked example is a value, and a value next to this input is a nudge whatever
    produced it. The first refusal message read *"for example 11 May 2026"* — the demo
    booking's actual return date, and so the exact proposal blind entry exists to
    withhold, handed back in an error. Found by driving the screen in Chrome; the client
    hint had already been rewritten for the same reason, and this was the same mistake
    reaching the same pixel from the server side.

    Written as a scan for anything date-shaped rather than for that one string, because
    the defect is the *class* of message, not the sentence that happened to carry it.
    """
    import re

    case_id, claim = _case_with_claim(api, db_session)

    refused = _review(api, case_id, claim.id, entered_value="03/04/2025")

    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert not re.search(r"\d{1,2} [A-Z][a-z]+ \d{4}", detail), detail
    assert not re.search(r"\d{4}-\d{2}-\d{2}", detail), detail
    # It still says what *would* work — refusing without naming an acceptable form is a
    # dead end, which is why the message exists at all.
    assert "YYYY-MM-DD" in detail


def test_a_closed_but_undecided_claim_keeps_its_proposal_hidden(
    api: Api, db_session: Session
) -> None:
    """The hinge itself, which the test above cannot reach.

    `test_a_proposal_is_withheld_until_it_is_decided_and_shown_afterwards` moves a claim
    from pending to decided in one step, so "not pending" and "has a decision" are the
    same thing throughout it — and the reveal passed whichever of the two it keyed off.
    The slice-3b trust review pointed out that a test which cannot separate two
    predicates cannot pin the choice between them.

    `INVALIDATED` separates them: the claim is closed, nobody decided anything, and the
    original reason for withholding — that a person is going to be asked to read this
    field off the document — has not been discharged. It is only unreachable through the
    API today because an invalidated claim's document is being deleted, which is luck
    rather than design.
    """
    from app.facts.domain import ClaimStatus
    from app.facts.schemas import ClaimView

    _case_id, claim = _case_with_claim(api, db_session, raw="10 May 2026")
    claim.status = ClaimStatus.INVALIDATED.value
    db_session.flush()

    view = ClaimView.of(claim, None)

    assert view.status == "INVALIDATED"
    assert view.decision is None
    assert view.proposed_value is None, (
        "a closed claim nobody decided about revealed the model's reading"
    )
    assert view.normalised_value is None


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_a_correction_that_carries_no_value_creates_no_fact(
    api: Api, db_session: Session, empty: str | None
) -> None:
    """A trusted fact asserting nothing is worse than no fact.

    `entered_value` is optional with no minimum length, and the pre-filled branch passed
    it straight through — so `{"decision": "CORRECT"}` with an empty box produced a
    `FactVersion` whose `raw_value` was `""`, stamped `USER_CORRECTED_AI_CLAIM`, with an
    evidence link marked available behind it. Three clicks from the review screen:
    Correct, select all, delete, Save.

    `extraction_service` already refuses to *propose* a blank — "a review queue must not
    ask someone to decide about a blank" — and this was the same rule missing from the
    other end of the same path. Found by the slice-3b trust review.

    Whitespace counts as empty, which also means a "correction" differing from the
    proposal only by spacing is refused rather than recorded as a change nobody made.
    """
    body: dict[str, object] = {"decision": "CORRECT"}
    if empty is not None:
        body["entered_value"] = empty

    case_id, claim = _case_with_claim(
        api, db_session, claim_type=ClaimType.TRAVEL_ORIGIN, raw="London Gatwick", model_iso=None
    )

    refused = api("user_a").post(f"/api/v1/cases/{case_id}/claims/{claim.id}/review", json=body)

    assert refused.status_code == 422
    assert refused.json()["code"] == "INCOMPLETE_REVIEW"
    db_session.expire_all()
    assert db_session.execute(select(FactVersion)).scalar_one_or_none() is None
    assert db_session.get(ExtractedClaim, claim.id).status == "PENDING_REVIEW"  # type: ignore[union-attr]


def test_a_decision_with_no_value_cannot_produce_a_reviewed_value(db_session: Session) -> None:
    """The second layer, at the type boundary rather than at the request.

    `outcome()` read `self.corrected_raw or ""`, so a decision that authorised nothing
    still handed back a `ReviewedValue` — and `ReviewedValue` is the one thing a
    `FactVersion` can be built from. There is no value it can carry meaning "nothing",
    which is exactly why this method already raises for a rejection. A row written by
    some future path that skips `_resolve` now hits the same refusal.
    """
    from app.facts.domain import ClaimReviewDecision, ReviewDecision, ReviewMode

    decision = ClaimReviewDecision(
        case_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        decision=ReviewDecision.CORRECT.value,
        review_mode=ReviewMode.PREFILLED.value,
        corrected_raw="",
        corrected_normalised=None,
        reviewed_by="user_a",
        reviewed_at=datetime.now(UTC),
    )
    decision.id = uuid.uuid4()

    with pytest.raises(ValueError, match="must carry one"):
        decision.outcome(schema=ValueSchema.TEXT_V1)
