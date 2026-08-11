"""Response schemas for the requirements and assessment endpoints.

The API returns conclusion and currency as **separate fields** (never merged): a
requirement can be SUPPORTED and STALE at once. A requirement with no result yet reads
as NOT_YET_ASSESSED with a null currency — the honest "not looked at yet" state, distinct
from any concluded outcome.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.assessments.domain import AssessmentInputLink, AssessmentResult, AssessmentRun
from app.requirements.domain import Conclusion
from app.requirements.models import RequirementDefinition


class RequirementSummary(BaseModel):
    requirement_key: str
    title: str
    group_key: str
    display_order: int
    conclusion: str
    currency: str | None
    summary_code: str | None
    updated_at: datetime | None

    @classmethod
    def from_projection(
        cls, definition: RequirementDefinition, result: AssessmentResult | None
    ) -> "RequirementSummary":
        return cls(
            requirement_key=definition.requirement_key,
            title=definition.title,
            group_key=definition.group_key,
            display_order=definition.display_order,
            conclusion=result.conclusion if result else Conclusion.NOT_YET_ASSESSED.value,
            currency=result.currency if result else None,
            summary_code=result.summary_code if result else None,
            updated_at=result.created_at if result else None,
        )


class InputLinkView(BaseModel):
    input_kind: str
    input_version_id: uuid.UUID
    input_key: str | None
    contribution_role: str


class ResultHistoryView(BaseModel):
    assessment_run_id: uuid.UUID
    conclusion: str
    currency: str
    summary_code: str | None
    created_at: datetime


class RequirementDetail(BaseModel):
    requirement_key: str
    title: str
    group_key: str
    short_description: str | None
    conclusion: str
    currency: str | None
    summary_code: str | None
    summary_parameters: dict[str, object]
    calculation_breakdown: dict[str, object]
    input_links: list[InputLinkView]
    guidance: list[dict[str, str]]
    history: list[ResultHistoryView]

    @classmethod
    def from_view(
        cls,
        definition: RequirementDefinition,
        current: AssessmentResult | None,
        input_links: list[AssessmentInputLink],
        guidance: list[dict[str, str]],
        history: list[AssessmentResult],
    ) -> "RequirementDetail":
        return cls(
            requirement_key=definition.requirement_key,
            title=definition.title,
            group_key=definition.group_key,
            short_description=definition.short_description,
            conclusion=current.conclusion if current else Conclusion.NOT_YET_ASSESSED.value,
            currency=current.currency if current else None,
            summary_code=current.summary_code if current else None,
            summary_parameters=dict(current.summary_parameters) if current else {},
            calculation_breakdown=dict(current.calculation_breakdown) if current else {},
            input_links=[
                InputLinkView(
                    input_kind=link.input_kind,
                    input_version_id=link.input_version_id,
                    input_key=link.input_key,
                    contribution_role=link.contribution_role,
                )
                for link in input_links
            ],
            guidance=guidance,
            history=[
                ResultHistoryView(
                    assessment_run_id=item.assessment_run_id,
                    conclusion=item.conclusion,
                    currency=item.currency,
                    summary_code=item.summary_code,
                    created_at=item.created_at,
                )
                for item in history
            ],
        )


class RecalculateResponse(BaseModel):
    assessment_run_id: uuid.UUID
    mode: str
    trigger_type: str
    result_count: int
    requirements: list[RequirementSummary]

    @classmethod
    def from_outcome(
        cls,
        run: AssessmentRun,
        requirements: list[tuple[RequirementDefinition, AssessmentResult | None]],
        result_count: int,
    ) -> "RecalculateResponse":
        return cls(
            assessment_run_id=run.id,
            mode=run.mode,
            trigger_type=run.trigger_type,
            result_count=result_count,
            requirements=[
                RequirementSummary.from_projection(definition, result)
                for definition, result in requirements
            ],
        )
