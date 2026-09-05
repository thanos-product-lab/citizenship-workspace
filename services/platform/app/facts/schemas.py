"""The review API's shapes.

**The request for a high-risk claim has no field that could carry the proposal back.**
That is the blind-entry guarantee at the wire, not just in the UI: a client cannot
submit a confirmation it did not derive from something a person typed, because there is
nowhere to put "the value I am confirming". The server compares the entry against the
claim it already holds and works out which decision that was.

**The response for a high-risk claim does not include the proposed value either.** A
review screen that fetched the proposal could render it beside the empty input, which is
a pre-filled confirm with extra steps. `proposed_value` is `None` for those, and
`tests/facts/test_blind_entry.py` asserts it.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.facts.domain import (
    HIGH_RISK_CLAIM_TYPES,
    CaseFact,
    ClaimType,
    ExtractedClaim,
    FactVersion,
    RejectionReason,
    ReviewDecision,
)


class ClaimView(BaseModel):
    """One claim awaiting review."""

    id: uuid.UUID
    claim_type: str
    journey_index: int
    value_schema_version: str
    #: **Null for a high-risk claim**, and that absence is the feature. Sending it would
    #: let a client render the model's answer beside the empty box a person is meant to
    #: fill from the document, which is the rubber stamp this design removes.
    proposed_value: str | None
    #: Whether the model could read the written date at all. Null here with a
    #: `date.v1` schema is what an ambiguous date looks like from outside, and the
    #: reason the human's reading is the only one that can settle it.
    normalised_value: str | None
    #: Whether this field must be confirmed blind. The client reads this rather than
    #: keeping its own copy of the high-risk list, which would be a second list to drift.
    requires_blind_entry: bool
    model_confidence: float | None
    source_locator: dict[str, object] | None
    status: str
    created_at: datetime

    @classmethod
    def of(cls, claim: ExtractedClaim) -> "ClaimView":
        blind = ClaimType(claim.claim_type) in HIGH_RISK_CLAIM_TYPES
        return cls(
            id=claim.id,
            claim_type=claim.claim_type,
            journey_index=claim.journey_index,
            value_schema_version=claim.value_schema_version,
            proposed_value=None if blind else claim.proposed_raw,
            normalised_value=None if blind else claim.normalised_value,
            requires_blind_entry=blind,
            model_confidence=claim.model_confidence,
            source_locator=claim.source_locator,
            status=claim.status,
            created_at=claim.created_at,
        )


class ReviewRequest(BaseModel):
    """A decision about one claim.

    For a **high-risk** claim: send `entered_value` — what the person read — and leave
    `decision` unset. The server derives CONFIRM or CORRECT from whether the entry
    matches, and there is no field in which a client could assert which it was.

    For the rest: send `decision`, plus `entered_value` when correcting.

    Rejection works for both: send `decision=REJECT` and a `reason_code`. "This date is
    not in this document" is a real answer, and demanding a typed value for it would
    force someone to invent one.
    """

    entered_value: str | None = Field(default=None, max_length=500)
    decision: ReviewDecision | None = None
    reason_code: RejectionReason | None = None
    # No `expected_revision`. It was here and it was decorative: `ExtractedClaim` has no
    # revision column, `ClaimView` exposed none, so no client could send a meaningful
    # value and nothing compared the one it did send. A field promising optimistic
    # concurrency and delivering none is worse than no field — it is a guarantee
    # somebody will rely on. The real serialisation is the row lock in `review()` and
    # `uq_claim_review_decisions_claim` (migration 0033).


class ReviewResponse(BaseModel):
    claim_id: uuid.UUID
    claim_status: str
    decision: str
    review_mode: str
    #: Null for a rejection, because a rejection creates no trusted fact.
    fact_version_id: uuid.UUID | None
    fact_version_number: int | None
    #: What the fact now says. Present so the client can show the outcome without a
    #: second request — and so a correction's result is visible immediately, which is
    #: the moment a user most needs to see that their value won.
    value: str | None


class FactView(BaseModel):
    """A trusted value, with where its trust came from."""

    fact_id: uuid.UUID
    fact_type: str
    version_number: int
    value: str
    normalised_value: str | None
    #: `USER_ENTERED`, `USER_CONFIRMED_AI_CLAIM`, `USER_CORRECTED_AI_CLAIM` or
    #: `DETERMINISTIC_DERIVATION`. Shown, because "who decided this" is the question the
    #: whole product exists to be able to answer (RFC §14).
    source_method: str
    created_at: datetime

    @classmethod
    def of(cls, fact: CaseFact, version: FactVersion) -> "FactView":
        return cls(
            fact_id=fact.id,
            fact_type=fact.fact_type,
            version_number=version.version_number,
            value=version.raw_value,
            normalised_value=version.normalised_value,
            source_method=version.source_method,
            created_at=version.created_at,
        )


class ClaimQueueResponse(BaseModel):
    items: list[ClaimView]


class FactsResponse(BaseModel):
    items: list[FactView]
