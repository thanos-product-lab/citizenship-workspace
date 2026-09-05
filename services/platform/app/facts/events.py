"""Domain events from the claim→fact path.

Carries ids and enum values only — never a claim's value, a corrected value, or any
fragment of a document. An event is written to `domain_events`, relayed through Redis
and read by whatever consumes it later; CLAUDE.md §11 keeps document content out of all
three, and "the value that was confirmed" is document content.
"""

import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

from app.shared.messaging import DomainEvent


@dataclass(frozen=True)
class ClaimReviewed(DomainEvent):
    """A human decided about a model's proposal.

    `fact_version_id` is None for a rejection, which is how a consumer tells "decided,
    and it created nothing" from "decided, and here is what it created" — the difference
    prime directive 1 turns on.

    `review_mode` rides along because it is what makes AI_EVALUATION_PLAN §15's
    confirmed-without-change rate mean anything: under `PREFILLED` that rate measures
    button placement, and under `BLIND_ENTRY` it measures agreement between a model and
    a person who read the document.
    """

    aggregate_type: ClassVar[str] = "ExtractedClaim"
    event_type: ClassVar[str] = "ClaimReviewed"

    case_id: uuid.UUID
    claim_type: str
    decision: str
    review_mode: str
    fact_version_id: uuid.UUID | None

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "claim_id": str(self.aggregate_id),
            "claim_type": self.claim_type,
            "decision": self.decision,
            "review_mode": self.review_mode,
            "fact_version_id": str(self.fact_version_id) if self.fact_version_id else None,
        }


@dataclass(frozen=True)
class FactSupportWithdrawn(DomainEvent):
    """The evidence behind a trusted fact went away.

    Its own event rather than a flag on the deletion event, for the reason
    `EvidenceDetachedFromTravelRecord` gives: the fact still holds — RFC §19 is explicit
    that deleting evidence does not delete a confirmed fact — and what changed is that a
    conclusion drawn from it now rests on something nobody can look at.
    """

    aggregate_type: ClassVar[str] = "FactVersion"
    event_type: ClassVar[str] = "FactSupportWithdrawn"

    case_id: uuid.UUID
    evidence_item_id: uuid.UUID
    link_id: uuid.UUID
    availability: str

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "fact_version_id": str(self.aggregate_id),
            "evidence_item_id": str(self.evidence_item_id),
            "link_id": str(self.link_id),
            "availability": self.availability,
        }


@dataclass(frozen=True)
class ClaimInvalidated(DomainEvent):
    """A proposal was closed unreviewed because its document is being deleted.

    Distinct from `ClaimReviewed` with a rejection, and the distinction is the point: a
    rejection is a human saying *"the model read this wrong"*, and this is the system
    saying *"nobody will ever get to say"*. Collapsing them would put a decision in the
    record that no person took.

    `claim_type` and nothing else about the value — the words the model read are the
    document's, and this event outlives it.
    """

    aggregate_type: ClassVar[str] = "ExtractedClaim"
    event_type: ClassVar[str] = "ClaimInvalidated"

    case_id: uuid.UUID
    evidence_item_id: uuid.UUID
    claim_type: str

    def payload(self) -> dict[str, Any]:
        return {
            "case_id": str(self.case_id),
            "claim_id": str(self.aggregate_id),
            "evidence_item_id": str(self.evidence_item_id),
            "claim_type": self.claim_type,
        }
