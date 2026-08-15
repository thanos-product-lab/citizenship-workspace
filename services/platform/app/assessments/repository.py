"""Persistence access for the assessment graph and the requirement catalog it reads.

Exposes domain intent, not generic CRUD: "the current result for this requirement",
"the catalogue with each requirement's current result", "this requirement's history".
The catalog reads (definition-by-key, active rule version) are here too so the service
resolves a requirement key to its ids through one seam.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult, AssessmentRun
from app.requirements.domain import Currency
from app.requirements.evaluation import RESIDENCE_REQUIREMENT_KEYS
from app.requirements.models import (
    RequirementDefinition,
    RuleDependencyDefinition,
    RuleLifecycleStatus,
    RuleVersion,
)

# Currencies of a result that can still be superseded by a recalculation (i.e. not already
# superseded). At most one such result exists per case + requirement.
_SUPERSEDABLE = (Currency.CURRENT.value, Currency.STALE.value)


class RequirementCatalogRepository:
    @staticmethod
    def get_definition_by_key(session: Session, key: str) -> RequirementDefinition | None:
        return session.scalar(
            select(RequirementDefinition).where(RequirementDefinition.requirement_key == key)
        )

    @staticmethod
    def list_definitions(session: Session) -> list[RequirementDefinition]:
        return list(
            session.scalars(
                select(RequirementDefinition).order_by(RequirementDefinition.display_order)
            )
        )

    @staticmethod
    def get_active_rule_version(session: Session, requirement_id: uuid.UUID) -> RuleVersion | None:
        """The current active rule version for a requirement. Exactly one is active for a
        given effective date (Domain §24.2); newest effective wins if that ever changes."""
        return session.scalar(
            select(RuleVersion)
            .where(
                RuleVersion.requirement_id == requirement_id,
                RuleVersion.lifecycle_status == RuleLifecycleStatus.ACTIVE.value,
            )
            .order_by(RuleVersion.effective_from.desc())
        )

    @staticmethod
    def list_dependencies(
        session: Session, rule_version_id: uuid.UUID
    ) -> list[RuleDependencyDefinition]:
        return list(
            session.scalars(
                select(RuleDependencyDefinition).where(
                    RuleDependencyDefinition.rule_version_id == rule_version_id
                )
            )
        )

    @staticmethod
    def count_definitions(session: Session) -> int:
        """How many requirements the catalogue holds — the denominator for "are any still
        unassessed", used by the case-phase derivation."""
        return session.scalar(select(func.count()).select_from(RequirementDefinition)) or 0

    @staticmethod
    def get_rule_version(session: Session, rule_version_id: uuid.UUID) -> RuleVersion | None:
        """The exact rule version a result was evaluated under. The detail screen shows this
        one, not the requirement's currently-active rule — a historical result must display
        the rule that actually produced it (Domain §30.5)."""
        return session.get(RuleVersion, rule_version_id)

    @staticmethod
    def get_guidance(session: Session, rule_version_id: uuid.UUID) -> list[dict[str, str]]:
        version = session.get(RuleVersion, rule_version_id)
        if version is None:
            return []
        guidance = version.configuration.get("guidance", [])
        return guidance if isinstance(guidance, list) else []


class AssessmentRepository:
    @staticmethod
    def add_run(session: Session, run: AssessmentRun) -> None:
        session.add(run)

    @staticmethod
    def add_result(session: Session, result: AssessmentResult) -> None:
        session.add(result)

    @staticmethod
    def add_input_link(session: Session, link: AssessmentInputLink) -> None:
        session.add(link)

    @staticmethod
    def get_run(session: Session, run_id: uuid.UUID) -> AssessmentRun | None:
        return session.get(AssessmentRun, run_id)

    @staticmethod
    def get_current_for_requirement(
        session: Session, case_id: uuid.UUID, requirement_id: uuid.UUID
    ) -> AssessmentResult | None:
        return session.scalar(
            select(AssessmentResult).where(
                AssessmentResult.case_id == case_id,
                AssessmentResult.requirement_id == requirement_id,
                AssessmentResult.currency == Currency.CURRENT.value,
            )
        )

    @staticmethod
    def get_supersedable_for_requirement(
        session: Session, case_id: uuid.UUID, requirement_id: uuid.UUID
    ) -> AssessmentResult | None:
        """The one non-superseded result for a requirement — CURRENT or STALE. A recalculation
        supersedes this, so a result marked STALE (input changed) is still replaced correctly
        rather than left orphaned when the new current result is written. Ordered newest-first
        so that if the at-most-one invariant were ever broken, the newest wins deterministically
        rather than an arbitrary row being picked silently."""
        return session.scalar(
            select(AssessmentResult)
            .where(
                AssessmentResult.case_id == case_id,
                AssessmentResult.requirement_id == requirement_id,
                AssessmentResult.currency.in_(_SUPERSEDABLE),
            )
            .order_by(AssessmentResult.created_at.desc())
        )

    @staticmethod
    def mark_current_residence_results_stale(
        session: Session, case_id: uuid.UUID, reason_code: str, at: datetime
    ) -> list[uuid.UUID]:
        """Blunt invalidation (M3B): mark every CURRENT residence-group result STALE. Returns
        the affected result ids. Selective, per-dependency invalidation is M6 (ADR-0008)."""
        residence_ids = select(RequirementDefinition.id).where(
            RequirementDefinition.requirement_key.in_(RESIDENCE_REQUIREMENT_KEYS)
        )
        results = session.scalars(
            select(AssessmentResult).where(
                AssessmentResult.case_id == case_id,
                AssessmentResult.requirement_id.in_(residence_ids),
                AssessmentResult.currency == Currency.CURRENT.value,
            )
        ).all()
        for result in results:
            result.mark_stale(reason_code=reason_code, at=at)
        return [result.id for result in results]

    @staticmethod
    def list_requirements_with_active_result(
        session: Session, case_id: uuid.UUID
    ) -> list[tuple[RequirementDefinition, AssessmentResult | None]]:
        """Every catalogued requirement with its displayed result — the non-superseded one,
        CURRENT or STALE — or None where none exists yet, in display order. A STALE result is
        shown (with its conclusion) so the user sees the last conclusion flagged for recalc
        (Domain §41.4), never silently hidden."""
        stmt = (
            select(RequirementDefinition, AssessmentResult)
            .outerjoin(
                AssessmentResult,
                and_(
                    AssessmentResult.requirement_id == RequirementDefinition.id,
                    AssessmentResult.case_id == case_id,
                    AssessmentResult.currency.in_(_SUPERSEDABLE),
                ),
            )
            .order_by(RequirementDefinition.display_order)
        )
        return [(definition, result) for definition, result in session.execute(stmt)]

    @staticmethod
    def list_displayed_states_by_case(
        session: Session, case_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[str, str]]]:
        """Every case's displayed (non-superseded) results as `(conclusion, currency)` pairs,
        in **one query** for all the given cases — the case list would otherwise issue a
        query per case to derive its phase. Cases with no results are absent from the dict.

        Conclusion and currency are returned as a pair and never merged (ADR-0001); the
        phase derivation reads both independently.
        """
        if not case_ids:
            return {}
        rows = session.execute(
            select(
                AssessmentResult.case_id,
                AssessmentResult.conclusion,
                AssessmentResult.currency,
            ).where(
                AssessmentResult.case_id.in_(case_ids),
                AssessmentResult.currency.in_(_SUPERSEDABLE),
            )
        )
        states: dict[uuid.UUID, list[tuple[str, str]]] = {}
        for case_id, conclusion, currency in rows:
            states.setdefault(case_id, []).append((conclusion, currency))
        return states

    @staticmethod
    def list_history_for_requirement(
        session: Session, case_id: uuid.UUID, requirement_id: uuid.UUID
    ) -> list[AssessmentResult]:
        """All results for a requirement, newest first — current plus every superseded or
        stale predecessor, so history stays inspectable (Domain §30.5)."""
        return list(
            session.scalars(
                select(AssessmentResult)
                .where(
                    AssessmentResult.case_id == case_id,
                    AssessmentResult.requirement_id == requirement_id,
                )
                .order_by(AssessmentResult.created_at.desc())
            )
        )

    @staticmethod
    def list_input_links(session: Session, result_id: uuid.UUID) -> list[AssessmentInputLink]:
        return list(
            session.scalars(
                select(AssessmentInputLink).where(
                    AssessmentInputLink.assessment_result_id == result_id
                )
            )
        )
