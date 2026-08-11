"""Persistence access for the assessment graph and the requirement catalog it reads.

Exposes domain intent, not generic CRUD: "the current result for this requirement",
"the catalogue with each requirement's current result", "this requirement's history".
The catalog reads (definition-by-key, active rule version) are here too so the service
resolves a requirement key to its ids through one seam.
"""

import uuid

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult, AssessmentRun
from app.requirements.domain import Currency
from app.requirements.models import (
    RequirementDefinition,
    RuleDependencyDefinition,
    RuleLifecycleStatus,
    RuleVersion,
)


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
    def list_requirements_with_current(
        session: Session, case_id: uuid.UUID
    ) -> list[tuple[RequirementDefinition, AssessmentResult | None]]:
        """Every catalogued requirement with its current result, or None where none exists
        yet — the shape the requirements list projection needs, in display order."""
        stmt = (
            select(RequirementDefinition, AssessmentResult)
            .outerjoin(
                AssessmentResult,
                and_(
                    AssessmentResult.requirement_id == RequirementDefinition.id,
                    AssessmentResult.case_id == case_id,
                    AssessmentResult.currency == Currency.CURRENT.value,
                ),
            )
            .order_by(RequirementDefinition.display_order)
        )
        return [(definition, result) for definition, result in session.execute(stmt)]

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
