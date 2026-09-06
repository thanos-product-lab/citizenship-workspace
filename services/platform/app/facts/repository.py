"""Reads and appends over claims and facts. Domain intent, never generic CRUD.

Two absences are the point.

**No update on a claim.** `ExtractedClaim` has no repository method that changes
`proposed_raw`, because a correction must not rewrite what the model said — it writes
`corrected_raw` on the decision instead (CLAUDE.md §9: *"correcting a claim preserves
the original proposal"*).

**No method returns a claim to a trusted consumer.** `list_pending_for_case` and
`get_for_case` return `ExtractedClaim`, a type the assessment path has no parameter
for; `current_for_case` returns `FactVersion`. Nothing here can hand a proposal to
something expecting a fact.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.facts.domain import (
    CaseFact,
    ClaimReviewDecision,
    ClaimStatus,
    ExtractedClaim,
    FactEvidenceLink,
    FactVersion,
    LinkAvailability,
)
from app.facts.values import ReviewedValue


class ClaimRepository:
    @staticmethod
    def get_for_case(
        session: Session, *, case_id: uuid.UUID, claim_id: uuid.UUID
    ) -> ExtractedClaim | None:
        return session.execute(
            select(ExtractedClaim).where(
                ExtractedClaim.id == claim_id, ExtractedClaim.case_id == case_id
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_for_update(
        session: Session, *, case_id: uuid.UUID, claim_id: uuid.UUID
    ) -> ExtractedClaim | None:
        """The same read, locked, for the command that decides about the claim.

        A separate method rather than a flag, so a reader cannot take the lock by
        accident and a writer cannot skip it by leaving an argument off. `review()` is
        the only caller and the only thing that should be.

        Without it, two concurrent reviews of one claim both saw `PENDING_REVIEW` under
        READ COMMITTED and both went on to create a trusted fact — one proposal, two
        answers, no error anywhere.
        """
        return session.execute(
            select(ExtractedClaim)
            .where(ExtractedClaim.id == claim_id, ExtractedClaim.case_id == case_id)
            .with_for_update()
        ).scalar_one_or_none()

    @staticmethod
    def list_pending_for_case(session: Session, *, case_id: uuid.UUID) -> list[ExtractedClaim]:
        """The review queue.

        `PENDING_REVIEW` only. A rejected or superseded claim is history — showing it in
        a queue would invite someone to decide about it twice, and the second decision
        would either duplicate a fact or resurrect a refusal.
        """
        return list(
            session.execute(
                select(ExtractedClaim)
                .where(
                    ExtractedClaim.case_id == case_id,
                    ExtractedClaim.status == ClaimStatus.PENDING_REVIEW.value,
                )
                .order_by(ExtractedClaim.created_at, ExtractedClaim.journey_index)
            ).scalars()
        )

    @staticmethod
    def pending_for_evidence_item(
        session: Session, *, case_id: uuid.UUID, evidence_item_id: uuid.UUID
    ) -> list[ExtractedClaim]:
        """The claims from one document that nobody has decided about yet.

        Named for the intent that uses it — deletion invalidating what is still open —
        rather than as a filter argument on the list above, so that a caller cannot
        accidentally sweep settled claims into it.
        """
        return list(
            session.execute(
                select(ExtractedClaim).where(
                    ExtractedClaim.case_id == case_id,
                    ExtractedClaim.evidence_item_id == evidence_item_id,
                    ExtractedClaim.status == ClaimStatus.PENDING_REVIEW.value,
                )
            ).scalars()
        )

    @staticmethod
    def decisions_by_claim(
        session: Session, *, case_id: uuid.UUID, claim_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ClaimReviewDecision]:
        """The decision that settled each of these claims, keyed by claim.

        One query for a whole document rather than one per field: the review screen
        renders every claim a booking proposed, and a per-claim lookup would be six
        round trips to draw one page.

        At most one decision per claim by `uq_claim_review_decisions_claim` (migration
        0033), so a dict is the honest shape and not a convenient lie.
        """
        if not claim_ids:
            return {}
        rows = session.execute(
            select(ClaimReviewDecision).where(
                ClaimReviewDecision.case_id == case_id,
                ClaimReviewDecision.claim_id.in_(claim_ids),
            )
        ).scalars()
        return {row.claim_id: row for row in rows}

    @staticmethod
    def list_for_evidence_item(
        session: Session, *, case_id: uuid.UUID, evidence_item_id: uuid.UUID
    ) -> list[ExtractedClaim]:
        """Every claim from one document, in any status — the document's own history."""
        return list(
            session.execute(
                select(ExtractedClaim)
                .where(
                    ExtractedClaim.case_id == case_id,
                    ExtractedClaim.evidence_item_id == evidence_item_id,
                )
                .order_by(ExtractedClaim.journey_index, ExtractedClaim.claim_type)
            ).scalars()
        )


class FactLinkRepository:
    @staticmethod
    def live_for_evidence_item(
        session: Session, *, case_id: uuid.UUID, evidence_item_id: uuid.UUID
    ) -> list[FactEvidenceLink]:
        """Every still-available link pointing at one document.

        Live only. A link already withdrawn is history, and withdrawing it twice would
        overwrite the timestamp that says when the support actually went.
        """
        return list(
            session.execute(
                select(FactEvidenceLink).where(
                    FactEvidenceLink.case_id == case_id,
                    FactEvidenceLink.evidence_item_id == evidence_item_id,
                    FactEvidenceLink.availability_status == LinkAvailability.AVAILABLE.value,
                )
            ).scalars()
        )

    @staticmethod
    def for_fact_version(session: Session, *, fact_version_id: uuid.UUID) -> list[FactEvidenceLink]:
        """What one trusted value rests on, including withdrawn links — a fact that
        *used* to be evidenced is a different thing from one that never was, and only
        the first needs explaining."""
        return list(
            session.execute(
                select(FactEvidenceLink)
                .where(FactEvidenceLink.fact_version_id == fact_version_id)
                .order_by(FactEvidenceLink.created_at)
            ).scalars()
        )


class FactRepository:
    @staticmethod
    def append_version(
        session: Session,
        *,
        case_id: uuid.UUID,
        fact_type: str,
        scope_key: str,
        reviewed: ReviewedValue,
    ) -> tuple[CaseFact, FactVersion]:
        """Add a version to a fact, creating the fact if this is its first value.

        **Append, never update.** Changing a value writes a new version and points
        `current_version_id` at it; the old version is untouched, which is what lets a
        historical assessment keep referencing the exact value it was drawn from
        (CLAUDE.md §2.3).

        Takes a `ReviewedValue` rather than a claim or a string. That parameter type is
        the guarantee: the only way to obtain one is `ClaimReviewDecision.outcome()` on
        a flushed decision, so this function cannot be called with a proposal.

        `scope_key` is required rather than defaulted, because the failure it prevents
        is silent: defaulting it to `""` would resolve every journey of every booking to
        one `travel.departure_date` fact and let each confirmation supersede the last.
        A caller has to say what the fact is about.
        """
        fact = session.execute(
            select(CaseFact).where(
                CaseFact.case_id == case_id,
                CaseFact.fact_type == fact_type,
                CaseFact.scope_key == scope_key,
            )
        ).scalar_one_or_none()
        if fact is None:
            fact = CaseFact(case_id=case_id, fact_type=fact_type, scope_key=scope_key)
            session.add(fact)
            session.flush()

        previous = (
            session.get(FactVersion, fact.current_version_id) if fact.current_version_id else None
        )
        version = FactVersion.from_review(
            reviewed,
            case_fact_id=fact.id,
            version_number=(previous.version_number + 1) if previous else 1,
            supersedes=previous.id if previous else None,
        )
        session.add(version)
        session.flush()
        fact.current_version_id = version.id
        return fact, version

    @staticmethod
    def current_for_case(
        session: Session, *, case_id: uuid.UUID
    ) -> list[tuple[CaseFact, FactVersion]]:
        """Every fact's current value. Never a claim — the return type says so."""
        rows = session.execute(
            select(CaseFact, FactVersion)
            .join(FactVersion, FactVersion.id == CaseFact.current_version_id)
            .where(CaseFact.case_id == case_id)
            .order_by(CaseFact.fact_type)
        ).all()
        return [(fact, version) for fact, version in rows]

    @staticmethod
    def versions_of(session: Session, *, case_fact_id: uuid.UUID) -> list[FactVersion]:
        """Every version a fact has had, oldest first. The history a correction leaves."""
        return list(
            session.execute(
                select(FactVersion)
                .where(FactVersion.case_fact_id == case_fact_id)
                .order_by(FactVersion.version_number)
            ).scalars()
        )
