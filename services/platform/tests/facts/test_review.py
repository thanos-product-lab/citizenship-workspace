"""Reviewing a claim, through the API a client actually calls.

`test_boundary.py` asserts what cannot be done. This asserts what happens when someone
does the thing the product is for: reads a document, types what it says, and gets a
trusted fact with their name on it.

The blind-entry tests are the ones to read. Everything else in the milestone protects a
boundary; these are about whether the human on the other side of it was really asked.
"""

import uuid
from datetime import UTC, datetime

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
    """
    case_id, claim = _case_with_claim(api, db_session)

    response = _review(api, case_id, claim.id, entered_value="03/04/2025")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "UNREADABLE_ENTERED_VALUE"
    assert "11 May 2026" in body["detail"] or "2026-05-11" in body["detail"]


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
