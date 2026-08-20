"""Persistence access for the assessment graph and the requirement catalog it reads.

Exposes domain intent, not generic CRUD: "the current result for this requirement",
"the catalogue with each requirement's current result", "this requirement's history".
The catalog reads (definition-by-key, active rule version) are here too so the service
resolves a requirement key to its ids through one seam.
"""

import uuid
from collections.abc import Collection, Sequence
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult, AssessmentRun
from app.requirements.domain import Currency
from app.requirements.models import (
    RequirementDefinition,
    RuleCompositionEdge,
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
    def list_active_dependencies(session: Session) -> list[tuple[str, RuleDependencyDefinition]]:
        """Every ACTIVE rule's declared dependencies, paired with its requirement key.

        This is what selective invalidation resolves against, so it reads the same rows the
        strict-equality provenance test checks a result's input links against.

        Known gap: dependencies are read from the *currently active* rule version, not from
        the version that produced the result being invalidated. If a rule's v2 drops a
        dependency its v1 declared, a change to that input resolves against v2, misses the
        requirement, and a v1-produced result stays CURRENT while an input it genuinely read
        has moved. Not reachable today — every requirement has exactly one rule version and
        nothing emits `RULE_VERSION_CHANGED` (Domain §41.1 lists it as a trigger; no path
        exists). Closing it means joining dependencies to `AssessmentResult.rule_version_id`
        instead, and belongs with the first rule-set migration (M9).
        """
        return [
            (requirement_key, dependency)
            for requirement_key, dependency in session.execute(
                select(RequirementDefinition.requirement_key, RuleDependencyDefinition)
                .join(RuleVersion, RuleVersion.requirement_id == RequirementDefinition.id)
                .join(
                    RuleDependencyDefinition,
                    RuleDependencyDefinition.rule_version_id == RuleVersion.id,
                )
                .where(RuleVersion.lifecycle_status == RuleLifecycleStatus.ACTIVE.value)
            ).all()
        ]

    @staticmethod
    def list_active_composition_edges(session: Session) -> list[tuple[str, str]]:
        """(downstream requirement key, upstream requirement key) for every ACTIVE rule that
        composes another requirement's conclusion (§25.4)."""
        return [
            (downstream, upstream)
            for downstream, upstream in session.execute(
                select(
                    RequirementDefinition.requirement_key,
                    RuleCompositionEdge.upstream_requirement_key,
                )
                .join(RuleVersion, RuleVersion.requirement_id == RequirementDefinition.id)
                .join(
                    RuleCompositionEdge,
                    RuleCompositionEdge.rule_version_id == RuleVersion.id,
                )
                .where(RuleVersion.lifecycle_status == RuleLifecycleStatus.ACTIVE.value)
            ).all()
        ]

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
    def mark_named_results_stale(
        session: Session,
        case_id: uuid.UUID,
        requirement_keys: Collection[str],
        reason_code: str,
        at: datetime,
    ) -> list[tuple[str, uuid.UUID]]:
        """Mark the CURRENT results for exactly the named requirements STALE (Domain §41.2).
        Returns (requirement_key, result_id) pairs for those actually marked.

        **The caller owns the set, including composition closure.** This marks what it is
        given and resolves nothing — pass a set that has not been closed over
        `rule_composition_edges` and the composite silently stays CURRENT while the
        conclusion it composes has moved, which is the defect ADR-0014 exists to close. Use
        `invalidation.resolve_affected_requirements` to build the set; do not assemble one
        by hand at a call site.

        Only CURRENT rows are selected, so an already-STALE result keeps the reason code of
        the change that *ended* its currency rather than being overwritten by every later
        change. Superseded rows are never touched: staling one would rewrite history.
        """
        if not requirement_keys:
            return []
        rows = session.execute(
            select(RequirementDefinition.requirement_key, AssessmentResult)
            .join(AssessmentResult, AssessmentResult.requirement_id == RequirementDefinition.id)
            .where(
                RequirementDefinition.requirement_key.in_(tuple(requirement_keys)),
                AssessmentResult.case_id == case_id,
                AssessmentResult.currency == Currency.CURRENT.value,
            )
        ).all()
        for _, result in rows:
            result.mark_stale(reason_code=reason_code, at=at)
        return [(key, result.id) for key, result in rows]

    @staticmethod
    def list_travel_input_version_ids(
        session: Session, case_id: uuid.UUID, requirement_key: str
    ) -> list[uuid.UUID]:
        """The travel-record versions a requirement's displayed result recorded reading.

        This is the provenance graph answering "what did the rule actually look at" — which
        is how issue derivation tells a record the evaluator judged to be out of scope from
        one it has never seen. Both are absent from the limitation; only one of them is
        safe to describe as harmless.
        """
        return list(
            session.scalars(
                select(AssessmentInputLink.input_version_id)
                .join(
                    AssessmentResult,
                    AssessmentResult.id == AssessmentInputLink.assessment_result_id,
                )
                .join(
                    RequirementDefinition,
                    RequirementDefinition.id == AssessmentResult.requirement_id,
                )
                .where(
                    AssessmentResult.case_id == case_id,
                    RequirementDefinition.requirement_key == requirement_key,
                    AssessmentResult.currency.in_(_SUPERSEDABLE),
                    AssessmentInputLink.input_kind == "TRAVEL_RECORD_VERSION",
                )
            )
        )

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
