"""Claims, decisions, and the facts they become.

Both sides of the trust boundary live in one module deliberately. `ExtractedClaim` is
untrusted and `FactVersion` is trusted, and the *relationship between their types* is
the invariant this milestone exists to enforce — splitting them across a module edge
would put the two halves of one guarantee in two places and make the edge the thing
you have to reason about instead of the types.

Reading order: `values.py` first, which carries the boundary itself. This file is the
persistence and the state machines around it.
"""

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.facts.values import (
    ProposedValue,
    ReviewedValue,
    SourceMethod,
    UserEnteredValue,
    ValueSchema,
    normalise,
)
from app.shared.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ClaimType(StrEnum):
    """RFC §41.2, verbatim. Namespaced by category so a claim type names its own origin,
    and so two categories can hold a field of the same name without either becoming
    ambiguous."""

    IMMIGRATION_STATUS_GRANTED_ON = "immigration.status_granted_on"
    IMMIGRATION_DATE_OF_BIRTH = "immigration.date_of_birth"
    IMMIGRATION_STATUS_TYPE = "immigration.status_type"
    IMMIGRATION_HOLDER_NAME = "immigration.holder_name"
    IMMIGRATION_REFERENCE_NUMBER = "immigration.reference_number"

    ENGLISH_TEST_DATE = "english.test_date"
    ENGLISH_CEFR_LEVEL = "english.cefr_level"
    ENGLISH_OVERALL_RESULT = "english.overall_result"
    ENGLISH_PROVIDER = "english.provider"
    ENGLISH_CANDIDATE_NAME = "english.candidate_name"

    LIFE_IN_UK_TEST_DATE = "life_in_uk.test_date"
    LIFE_IN_UK_UNIQUE_REFERENCE = "life_in_uk.unique_reference"
    LIFE_IN_UK_OVERALL_RESULT = "life_in_uk.overall_result"
    LIFE_IN_UK_CANDIDATE_NAME = "life_in_uk.candidate_name"

    TRAVEL_DEPARTURE_DATE = "travel.departure_date"
    TRAVEL_RETURN_DATE = "travel.return_date"
    TRAVEL_ORIGIN = "travel.origin"
    TRAVEL_DESTINATION = "travel.destination"
    TRAVEL_BOOKING_REFERENCE = "travel.booking_reference"
    TRAVEL_TRAVELLER_NAME = "travel.traveller_name"


#: The value shape each claim type carries (RFC §41.2). Total over `ClaimType`, asserted
#: in `tests/facts/test_boundary.py` — a claim type with no schema could be created with
#: any shape at all, which is the one thing `value_schema_version` exists to prevent.
SCHEMA_FOR_CLAIM_TYPE: dict[ClaimType, ValueSchema] = {
    ClaimType.IMMIGRATION_STATUS_GRANTED_ON: ValueSchema.DATE_V1,
    ClaimType.IMMIGRATION_DATE_OF_BIRTH: ValueSchema.DATE_V1,
    ClaimType.IMMIGRATION_STATUS_TYPE: ValueSchema.TEXT_V1,
    ClaimType.IMMIGRATION_HOLDER_NAME: ValueSchema.TEXT_V1,
    ClaimType.IMMIGRATION_REFERENCE_NUMBER: ValueSchema.TEXT_V1,
    ClaimType.ENGLISH_TEST_DATE: ValueSchema.DATE_V1,
    ClaimType.ENGLISH_CEFR_LEVEL: ValueSchema.TEXT_V1,
    ClaimType.ENGLISH_OVERALL_RESULT: ValueSchema.TEXT_V1,
    ClaimType.ENGLISH_PROVIDER: ValueSchema.TEXT_V1,
    ClaimType.ENGLISH_CANDIDATE_NAME: ValueSchema.TEXT_V1,
    ClaimType.LIFE_IN_UK_TEST_DATE: ValueSchema.DATE_V1,
    ClaimType.LIFE_IN_UK_UNIQUE_REFERENCE: ValueSchema.TEXT_V1,
    ClaimType.LIFE_IN_UK_OVERALL_RESULT: ValueSchema.TEXT_V1,
    ClaimType.LIFE_IN_UK_CANDIDATE_NAME: ValueSchema.TEXT_V1,
    ClaimType.TRAVEL_DEPARTURE_DATE: ValueSchema.DATE_V1,
    ClaimType.TRAVEL_RETURN_DATE: ValueSchema.DATE_V1,
    ClaimType.TRAVEL_ORIGIN: ValueSchema.TEXT_V1,
    ClaimType.TRAVEL_DESTINATION: ValueSchema.TEXT_V1,
    ClaimType.TRAVEL_BOOKING_REFERENCE: ValueSchema.TEXT_V1,
    ClaimType.TRAVEL_TRAVELLER_NAME: ValueSchema.TEXT_V1,
}

#: RFC §41.3 — every `date.v1` claim type. Derived rather than listed, so a date field
#: added later is high-risk the moment it exists. A hand-kept copy would be a list
#: somebody forgets, and what it gates is blind confirmation and the bulk-confirm ban.
HIGH_RISK_CLAIM_TYPES = frozenset(
    claim_type
    for claim_type, schema in SCHEMA_FOR_CLAIM_TYPE.items()
    if schema is ValueSchema.DATE_V1
)


class ClaimStatus(StrEnum):
    """RFC §9. Status records review history; **it does not turn the claim into a fact**.

    A claim is `CONFIRMED` when a human confirmed it, and the fact that resulted is a
    different row in a different table with its own provenance. Reading this field as
    "trusted" is the mistake the whole module is shaped to prevent.
    """

    PENDING_REVIEW = "PENDING_REVIEW"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    INVALIDATED = "INVALIDATED"


#: Claim types whose fact identity needs a scope beyond the type itself, derived from
#: the namespace rather than listed — a new `travel.*` type joins automatically, and a
#: list is a thing to forget to update. Every other category describes the applicant
#: once per case, so its facts are case-level.
JOURNEY_SCOPED_CLAIM_TYPES: frozenset[ClaimType] = frozenset(
    claim_type for claim_type in ClaimType if claim_type.value.startswith("travel.")
)


#: Claims a user has not yet decided about. The only status a review may act on — acting
#: on any other would either duplicate a fact or resurrect a rejected proposal.
OPEN_STATUSES = frozenset({ClaimStatus.PENDING_REVIEW})


class ReviewDecision(StrEnum):
    """RFC §10. `DEFER` is not here: §10 permits it as a non-final UI state, and a
    non-final state persisted alongside final ones is a status people will read as an
    outcome."""

    CONFIRM = "CONFIRM"
    CORRECT = "CORRECT"
    REJECT = "REJECT"


class ReviewMode(StrEnum):
    """How the decision was taken (RFC §41.4).

    Recorded because it is what makes §15's confirmed-without-change rate mean anything.
    Under `PREFILLED`, that rate measures button placement; under `BLIND_ENTRY` it
    measures agreement between a model and a human who read the document.
    """

    BLIND_ENTRY = "BLIND_ENTRY"
    PREFILLED = "PREFILLED"


class RejectionReason(StrEnum):
    """RFC §10. Structured, so "why was this wrong" is answerable across a corpus rather
    than only by reading prose one claim at a time (AI_EVALUATION_PLAN §15)."""

    VALUE_NOT_PRESENT = "VALUE_NOT_PRESENT"
    WRONG_FIELD = "WRONG_FIELD"
    WRONG_DOCUMENT = "WRONG_DOCUMENT"
    DUPLICATE = "DUPLICATE"
    AMBIGUOUS = "AMBIGUOUS"
    OTHER = "OTHER"


class SupportType(StrEnum):
    """RFC §12."""

    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONFLICTING = "CONFLICTING"
    USER_ASSERTED = "USER_ASSERTED"


class LinkAvailability(StrEnum):
    """Whether the evidence behind a fact is still there. `DELETED` is not `UNAVAILABLE`:
    one is a document that went away and one is a link withdrawn for another reason, and
    a user asking "why is this unsupported" needs them told apart."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    DELETED = "DELETED"


class ExtractedClaim(Base):
    """An immutable machine-proposed interpretation of one field (RFC §9).

    **Immutable in the way that matters.** `proposed_raw` has no setter and the
    repository exposes no update, so a correction cannot rewrite what the model said —
    it writes `corrected_raw` on the *decision*. CLAUDE.md §9: *"correcting a claim
    preserves the original proposal."*
    """

    __tablename__ = "extracted_claims"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.id"))
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("extraction_runs.id"), index=True
    )

    claim_type: Mapped[str] = mapped_column(String(60), index=True)
    #: Which journey on a multi-journey document this claim is about (RFC §41.2).
    #: Without it, a two-journey booking produces two `travel.departure_date` claims that
    #: nothing can tell apart.
    journey_index: Mapped[int] = mapped_column(Integer, default=0)

    value_schema_version: Mapped[str] = mapped_column(String(20))
    #: What the model said, verbatim. Written once.
    proposed_raw: Mapped[str] = mapped_column(String(500))
    #: The model's ISO reading of a date, kept for the record and **never used**: the
    #: deterministic normaliser decides `normalised_value` (RFC §41.1). Stored so a later
    #: evaluation can measure how often the two agreed.
    proposed_iso: Mapped[str | None] = mapped_column(String(40))
    #: The deterministic reading, or NULL when the written form does not determine one.
    #: A null here is what makes an ambiguous date reach a human undecided.
    normalised_value: Mapped[str | None] = mapped_column(String(200))

    status: Mapped[str] = mapped_column(String(20), index=True)
    #: Display metadata. Nothing branches on it (RFC §36).
    model_confidence: Mapped[float | None] = mapped_column()
    #: Where in the document this came from (RFC §9). JSONB because what a pipeline can
    #: offer varies — a native text layer gives a span, a scan may give only a page.
    source_locator: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    superseded_by_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extracted_claims.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def proposed_value(self) -> ProposedValue:
        """What the model said, as the type that cannot become a fact.

        A property rather than a column so that the *dangerous* object is what a caller
        naturally reaches for: `claim.proposed_value` is a `ProposedValue`, and there is
        nowhere to pass one that expects a `ReviewedValue`.
        """
        return ProposedValue(
            schema=ValueSchema(self.value_schema_version),
            raw=self.proposed_raw,
            model_iso=self.proposed_iso,
        )

    @property
    def is_high_risk(self) -> bool:
        """Whether this field must be confirmed blind (RFC §41.3/§41.4)."""
        return ClaimType(self.claim_type) in HIGH_RISK_CLAIM_TYPES

    def invalidate(self) -> bool:
        """The document this was read out of is being deleted.

        A proposal about a destroyed document must stop being reviewable *at deletion*,
        not at purge: from the moment access is blocked the user can no longer open the
        page and read what it says, and blind confirmation is the whole review
        interaction for a date. A claim left `PENDING_REVIEW` here would offer an empty
        input beside a source region nobody can fetch, and whatever the user typed would
        become a trusted fact backed by nothing — false reassurance produced by an
        omission rather than by a decision.

        Only from `PENDING_REVIEW`. A claim already confirmed, corrected or rejected is
        history, and rewriting a settled status would erase the record of a decision a
        human actually took. The fact that resulted is handled separately and correctly:
        it survives, and its `FactEvidenceLink` goes `DELETED`.

        Returns whether anything changed, so the caller can count.
        """
        if self.status != ClaimStatus.PENDING_REVIEW.value:
            return False
        self.status = ClaimStatus.INVALIDATED.value
        return True

    def redact(self) -> None:
        """Erase the document's own words after the bytes are gone (Domain §51.1 step 7).

        `proposed_raw` is verbatim text lifted out of the document — a traveller's name,
        a booking reference, a date as printed — so it is the document, in a second
        table, exactly as `evidence_file_texts` was. There is no minimal non-sensitive
        version of it. `proposed_iso` and `normalised_value` are readings of that same
        text and go with it.

        The row itself stays, cleared rather than deleted, for the reason
        `extraction_runs` stays: a confirmed fact's provenance chain runs decision →
        claim, and deleting the claim would leave a trusted value unable to say where its
        proposal came from. What remains — ids, `claim_type`, status, confidence — names
        no document and no person.
        """
        self.proposed_raw = ""
        self.proposed_iso = None
        self.normalised_value = None
        self.source_locator = None

    @classmethod
    def propose(
        cls,
        *,
        case_id: uuid.UUID,
        evidence_item_id: uuid.UUID,
        evidence_file_id: uuid.UUID,
        extraction_run_id: uuid.UUID,
        claim_type: ClaimType,
        value: ProposedValue,
        journey_index: int = 0,
        model_confidence: float | None = None,
        source_locator: dict[str, object] | None = None,
    ) -> "ExtractedClaim":
        """Create a claim. The only constructor, and it produces `PENDING_REVIEW` — there
        is no argument by which a claim can be born already confirmed."""
        expected = SCHEMA_FOR_CLAIM_TYPE[claim_type]
        if value.schema is not expected:
            raise ValueError(
                f"{claim_type.value} carries {expected.value}, not {value.schema.value}"
            )
        return cls(
            case_id=case_id,
            evidence_item_id=evidence_item_id,
            evidence_file_id=evidence_file_id,
            extraction_run_id=extraction_run_id,
            claim_type=claim_type.value,
            journey_index=journey_index,
            value_schema_version=value.schema.value,
            proposed_raw=value.raw[:500],
            proposed_iso=value.model_iso,
            normalised_value=normalise(value),
            status=ClaimStatus.PENDING_REVIEW.value,
            model_confidence=model_confidence,
            source_locator=source_locator,
        )


class ClaimReviewDecision(Base):
    """An immutable record of a human deciding about a claim (RFC §10).

    **The only producer of a `ReviewedValue`**, and therefore the only route from a
    proposal to a fact. `outcome()` requires `self.id`, which SQLAlchemy assigns on
    flush — so the decision is durable before the value that names it can exist.
    """

    __tablename__ = "claim_review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extracted_claims.id"), index=True)

    decision: Mapped[str] = mapped_column(String(20))
    #: How it was taken (RFC §41.4). `(CONFIRM, BLIND_ENTRY)` is confirm-as-proposed;
    #: `(CORRECT, BLIND_ENTRY)` is confirm-with-correction.
    review_mode: Mapped[str] = mapped_column(String(20))
    #: The user's value on a CORRECT. Written here rather than onto the claim, which is
    #: how the original proposal survives being corrected.
    corrected_raw: Mapped[str | None] = mapped_column(String(500))
    corrected_normalised: Mapped[str | None] = mapped_column(String(200))
    reason_code: Mapped[str | None] = mapped_column(String(30))

    reviewed_by: Mapped[str] = mapped_column(String(255))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    #: Which decision this is for the claim — always 1, enforced by
    #: `uq_claim_review_decisions_claim` (migration 0033). Kept as a column rather than
    #: dropped so the constraint has something legible beside it, and because §10's
    #: "a claim is decided once" is a statement worth being able to read off a row.
    #:
    #: It was named `claim_revision` and documented as optimistic concurrency, and it
    #: was neither: nothing ever compared it. Both slice-3a reviews found the same
    #: thing independently. The serialisation is now the row lock in `review()` plus the
    #: unique key — mechanisms that fail closed rather than a number nobody reads.
    decision_sequence: Mapped[int] = mapped_column(Integer, default=1)

    def outcome(self, *, schema: ValueSchema) -> ReviewedValue:
        """The reviewed value this decision authorises, or a refusal to produce one.

        Raises for `REJECT`, and that is the point rather than an inconvenience: a
        rejection creates no trusted fact (RFC §10), so there is no `ReviewedValue` for
        it to return and no way for a caller to obtain one by mistake.
        """
        decision = ReviewDecision(self.decision)
        if decision is ReviewDecision.REJECT:
            raise ValueError("a rejected claim authorises no value; REJECT creates no trusted fact")
        if self.id is None:  # pragma: no cover - flush assigns it
            raise RuntimeError(
                "the decision must be flushed before it can authorise a value: a fact "
                "may not reference a decision that is not yet durable"
            )

        corrected = decision is ReviewDecision.CORRECT
        return ReviewedValue(
            decision_id=self.id,
            claim_id=self.claim_id,
            schema=schema,
            raw=self.corrected_raw or "",
            normalised=self.corrected_normalised,
            source_method=(
                SourceMethod.USER_CORRECTED_AI_CLAIM
                if corrected
                else SourceMethod.USER_CONFIRMED_AI_CLAIM
            ),
            reviewed_by=self.reviewed_by,
            reviewed_at=self.reviewed_at,
        )


class CaseFact(Base):
    """The stable identity of one trusted concept (RFC §11). Values live in versions.

    **Identity is `(case_id, fact_type, scope_key)`, not `(case_id, fact_type)`.** A
    grant date is one thing per case and its scope key is empty. A departure date is
    not: a two-leg booking proposes `travel.departure_date` twice, and two bookings in
    one case propose it again — which is why `ExtractedClaim` carries `journey_index` at
    all (RFC §41.2).

    Without the scope key those all resolved to one fact, so confirming the second
    journey appended a version and moved `current_version_id` off the first. Nothing
    looked wrong: it is a legitimate-looking supersede chain, and the case's answer for
    "when did you leave" quietly became whichever claim was reviewed last. Found by the
    slice-3a trust review; every test in the suite happened to build one claim.
    """

    __tablename__ = "case_facts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    fact_type: Mapped[str] = mapped_column(String(60), index=True)
    #: What this fact is *about*, when the type alone does not say. Empty for a
    #: case-level fact; `"<evidence_item_id>:<journey_index>"` for a journey-scoped one.
    #:
    #: Scoped to the document rather than to the trip on purpose. Two bookings covering
    #: one trip should eventually converge, but deciding *that they are the same trip*
    #: is conflict detection (slice 4), not identity. Until then each document's reading
    #: is its own fact, which is the conservative failure: a duplicate to reconcile
    #: rather than a value silently replaced.
    scope_key: Mapped[str] = mapped_column(String(80), default="")
    #: App-maintained pointer, no circular FK — the 0003/0005 convention.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __mapper_args__ = {"version_id_col": revision}  # noqa: RUF012


class FactVersion(Base):
    """One immutable trusted value (RFC §11).

    **Two constructors, and no third.** `from_review` takes a `ReviewedValue`, which only
    a flushed `ClaimReviewDecision` can produce; `from_user_entry` takes a
    `UserEnteredValue`, which has no claim behind it because there was nothing to review.

    There is no `from_claim`. Handing `from_review` an `ExtractedClaim` — or its
    `proposed_value` — is a `just typecheck` failure, which is the guarantee prime
    directive 1 rests on. See `values.py`.
    """

    __tablename__ = "fact_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_fact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("case_facts.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)

    value_schema_version: Mapped[str] = mapped_column(String(20))
    raw_value: Mapped[str] = mapped_column(String(500))
    normalised_value: Mapped[str | None] = mapped_column(String(200))

    source_method: Mapped[str] = mapped_column(String(40))
    #: NOT NULL for the two review-derived methods, NULL for the others — enforced by a
    #: CHECK in migration 0030. An AI-derived fact cannot exist in the database without a
    #: decision row to point at.
    claim_review_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim_review_decisions.id")
    )
    supersedes_fact_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("fact_versions.id")
    )

    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @classmethod
    def from_review(
        cls,
        reviewed: ReviewedValue,
        *,
        case_fact_id: uuid.UUID,
        version_number: int,
        supersedes: uuid.UUID | None = None,
    ) -> "FactVersion":
        """A trusted value from a human's decision about a model's proposal.

        Takes a `ReviewedValue` and nothing else. That signature is prime directive 1:
        a `ProposedValue` is a different type, `ExtractedClaim` is a different type, and
        neither converts.
        """
        return cls(
            case_fact_id=case_fact_id,
            version_number=version_number,
            value_schema_version=reviewed.schema.value,
            raw_value=reviewed.raw[:500],
            normalised_value=reviewed.normalised,
            source_method=reviewed.source_method.value,
            claim_review_decision_id=reviewed.decision_id,
            supersedes_fact_version_id=supersedes,
            created_by=reviewed.reviewed_by,
        )

    @classmethod
    def from_user_entry(
        cls,
        entered: UserEnteredValue,
        *,
        case_fact_id: uuid.UUID,
        version_number: int,
        supersedes: uuid.UUID | None = None,
    ) -> "FactVersion":
        """A trusted value the user typed directly, with no model involved (RFC §13)."""
        return cls(
            case_fact_id=case_fact_id,
            version_number=version_number,
            value_schema_version=entered.schema.value,
            raw_value=entered.raw[:500],
            normalised_value=entered.normalised,
            source_method=SourceMethod.USER_ENTERED.value,
            claim_review_decision_id=None,
            supersedes_fact_version_id=supersedes,
            created_by=entered.entered_by,
        )


class FactEvidenceLink(Base):
    """What a fact rests on (RFC §12).

    The row that makes `Assessment → FactVersion → FactEvidenceLink → Evidence →
    ExtractedClaim → ExtractionRun` a chain you can walk, and the reason
    `evidence_service.mark_support_unavailable` has a second call from this slice on.
    """

    __tablename__ = "fact_evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    fact_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fact_versions.id"), index=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.id"))
    claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extracted_claims.id"))

    support_type: Mapped[str] = mapped_column(String(20))
    availability_status: Mapped[str] = mapped_column(String(20))
    #: Withdrawn links are kept, not deleted: a fact that *used* to be evidenced is a
    #: different thing from one that never was, and only the first needs explaining.
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def is_live(self) -> bool:
        return LinkAvailability(self.availability_status) is LinkAvailability.AVAILABLE

    def withdraw(self, *, availability: LinkAvailability, at: datetime) -> None:
        self.availability_status = availability.value
        self.withdrawn_at = at
