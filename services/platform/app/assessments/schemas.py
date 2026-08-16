"""Response schemas for the requirements and assessment endpoints.

The API returns conclusion and currency as **separate fields** (never merged): a
requirement can be SUPPORTED and STALE at once. A requirement with no result yet reads
as NOT_YET_ASSESSED with a null currency — the honest "not looked at yet" state, distinct
from any concluded outcome.
"""

import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.assessments.domain import AssessmentResult, AssessmentRun
from app.assessments.groups import GroupMember, GroupSummary
from app.assessments.priority import CandidateAction
from app.assessments.provenance import ResolvedInput
from app.requirements.domain import Conclusion, Currency
from app.requirements.evaluation import LinkInputKind
from app.requirements.messages import (
    render_limitation,
    render_next_action,
    render_stale_reason,
    render_summary,
)
from app.requirements.models import RequirementDefinition, RuleVersion

if TYPE_CHECKING:  # avoids a cycle: the service imports these schemas back
    from app.assessments.service import CaseOverviewView, RequirementDetailView


class RenderedMessage(BaseModel):
    """A code, its parameters, and the deterministic plain-language rendering of the two.

    All three travel together on purpose. `text` is what a user reads; `code` and
    `parameters` are what a client keys layout off and what a reviewer checks the wording
    against. `text` is null only when a code has no template — a packaging bug the client
    handles by showing the structured fields rather than inventing a sentence."""

    code: str
    parameters: dict[str, object]
    text: str | None

    @classmethod
    def build(
        cls,
        code: str | None,
        parameters: dict[str, object] | None,
        render: Callable[[str | None, dict[str, object] | None], str | None],
    ) -> "RenderedMessage | None":
        if code is None:
            return None
        return cls(code=code, parameters=dict(parameters or {}), text=render(code, parameters))


class StaleInformation(BaseModel):
    """Why a result is no longer current, and since when. Present only while
    `currency == STALE` — it explains that currency, and never modifies the conclusion."""

    reason_code: str | None
    reason: str | None
    marked_stale_at: datetime | None


class RequirementSummary(BaseModel):
    requirement_key: str
    title: str
    group_key: str
    display_order: int
    # Two independent axes, never merged (ADR-0001). `currency` is null — not "CURRENT" —
    # when there is no result at all, so "not looked at yet" cannot be mistaken for
    # "looked at, and up to date".
    conclusion: str
    currency: str | None
    summary_code: str | None
    summary: RenderedMessage | None
    stale: StaleInformation | None
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
            summary=(
                RenderedMessage.build(
                    result.summary_code, dict(result.summary_parameters), render_summary
                )
                if result
                else None
            ),
            stale=_stale_information(result),
            updated_at=result.created_at if result else None,
        )


def _stale_information(result: AssessmentResult | None) -> StaleInformation | None:
    """Only populated for a STALE result. A CURRENT result carries no stale block at all,
    so a client cannot render a stale notice over a conclusion that is still good."""
    if result is None or result.currency != Currency.STALE.value:
        return None
    return StaleInformation(
        reason_code=result.stale_reason_code,
        reason=render_stale_reason(result.stale_reason_code),
        marked_stale_at=result.marked_stale_at,
    )


class RequirementLink(BaseModel):
    """A requirement as the overview references it: enough to render its status and link
    to the full explanation, without duplicating the detail projection."""

    requirement_key: str
    title: str
    conclusion: str
    currency: str | None


class ResolvedInputView(BaseModel):
    """One versioned input a result read, described. The structural fields (`input_kind`,
    `input_version_id`, `contribution_role`) are the provenance record; the rest is what
    makes it readable. Both travel, so the client can render the description while the
    exact reference stays available and checkable."""

    input_kind: str
    input_key: str | None
    input_version_id: uuid.UUID
    contribution_role: str
    label: str
    value: str
    detail: str | None
    version_number: int | None
    #: False means this input has been edited since the result was produced — the specific
    #: thing that moved under a stale conclusion.
    is_still_current: bool
    #: True means the record was removed after this result was produced. Distinct from
    #: `is_still_current`, which a tombstone leaves true.
    is_removed: bool
    #: Whether this record passed the §6.1 trust gate and counted toward the trusted
    #: figure. Null where the gate does not apply. Never omit this: a list of travel
    #: inputs with no such marker reads as a list of corroboration.
    counts_as_confirmed: bool | None
    provenance_kind: str
    unavailable: bool

    @classmethod
    def of(cls, resolved: ResolvedInput) -> "ResolvedInputView":
        return cls(**asdict(resolved))


class LimitationView(BaseModel):
    """A structured condition reducing confidence (Domain §33), rendered. `affected_input_ids`
    names the exact versions responsible, so the UI can point at them in the inputs list."""

    code: str
    severity: str
    parameters: dict[str, object]
    text: str | None
    affected_input_ids: list[str]

    @classmethod
    def of(cls, raw: dict[str, object]) -> "LimitationView":
        code = str(raw.get("code", ""))
        parameters = raw.get("message_parameters")
        params = dict(parameters) if isinstance(parameters, dict) else {}
        affected = raw.get("affected_input_ids")
        return cls(
            code=code,
            severity=str(raw.get("severity", "")),
            parameters=params,
            text=render_limitation(code, params),
            affected_input_ids=[str(item) for item in affected]
            if isinstance(affected, list)
            else [],
        )


class NextActionView(BaseModel):
    """A structured action that would move the result forward (Domain §34), rendered."""

    code: str
    parameters: dict[str, object]
    text: str | None
    priority: int
    blocking: bool

    @classmethod
    def of(cls, raw: dict[str, object]) -> "NextActionView":
        code = str(raw.get("code", ""))
        parameters = raw.get("label_parameters")
        params = dict(parameters) if isinstance(parameters, dict) else {}
        priority = raw.get("priority")
        return cls(
            code=code,
            parameters=params,
            text=render_next_action(code, params),
            priority=priority if isinstance(priority, int) else 0,
            blocking=bool(raw.get("blocking", False)),
        )


class RuleView(BaseModel):
    """The rule version that produced the displayed result, and its guidance citations.

    `guidance_version_recorded` is deliberately present and deliberately false at M4.
    MVP §8.8 wants a guidance version and retrieval date on every source link; the
    `GuidanceVersion` tables that would carry them arrive with Migration 5 (ADR-0007).
    Rather than omit the question or fill it with the rule's own `effective_from` dressed
    up as a retrieval date, the API states that the value is not recorded yet and the UI
    says so. Fabricated provenance is the worst defect this product could ship.
    """

    semantic_version: str
    rule_set: str
    lifecycle_status: str
    effective_from: datetime
    guidance: list[dict[str, str]]
    guidance_version_recorded: bool = False

    @classmethod
    def of(cls, rule: RuleVersion, guidance: list[dict[str, str]]) -> "RuleView":
        return cls(
            semantic_version=rule.semantic_version,
            rule_set=rule.rule_set,
            lifecycle_status=rule.lifecycle_status,
            effective_from=rule.effective_from,
            guidance=guidance,
        )


class ResultHistoryView(BaseModel):
    assessment_run_id: uuid.UUID
    conclusion: str
    currency: str
    summary_code: str | None
    #: Carried so a change between two runs is legible. Without it the canonical
    #: 439 → 440 transition renders as "NEAR_THRESHOLD → NEAR_THRESHOLD", i.e. as nothing
    #: having happened.
    summary_parameters: dict[str, object]
    summary: RenderedMessage | None
    created_at: datetime

    @classmethod
    def of(cls, result: AssessmentResult) -> "ResultHistoryView":
        parameters = dict(result.summary_parameters)
        return cls(
            assessment_run_id=result.assessment_run_id,
            conclusion=result.conclusion,
            currency=result.currency,
            summary_code=result.summary_code,
            summary_parameters=parameters,
            summary=RenderedMessage.build(result.summary_code, parameters, render_summary),
            created_at=result.created_at,
        )


class RequirementDetail(BaseModel):
    requirement_key: str
    title: str
    group_key: str
    short_description: str | None
    conclusion: str
    currency: str | None
    summary_code: str | None
    summary_parameters: dict[str, object]
    summary: RenderedMessage | None
    stale: StaleInformation | None
    calculation_breakdown: dict[str, object]
    limitations: list[LimitationView]
    next_actions: list[NextActionView]
    #: The explanation stack splits inputs by what they are. `facts_used` is the route
    #: profile answers and the proposed application date; `travel_inputs` is the travel
    #: records. Both are resolved from the same link set and neither is filtered.
    facts_used: list[ResolvedInputView]
    travel_inputs: list[ResolvedInputView]
    rule: RuleView | None
    guidance: list[dict[str, str]]
    history: list[ResultHistoryView]

    @classmethod
    def from_view(cls, view: "RequirementDetailView") -> "RequirementDetail":
        current = view.current
        definition = view.definition
        resolved = [ResolvedInputView.of(item) for item in view.inputs]
        return cls(
            requirement_key=definition.requirement_key,
            title=definition.title,
            group_key=definition.group_key,
            short_description=definition.short_description,
            conclusion=current.conclusion if current else Conclusion.NOT_YET_ASSESSED.value,
            currency=current.currency if current else None,
            summary_code=current.summary_code if current else None,
            summary_parameters=dict(current.summary_parameters) if current else {},
            summary=(
                RenderedMessage.build(
                    current.summary_code, dict(current.summary_parameters), render_summary
                )
                if current
                else None
            ),
            stale=_stale_information(current),
            calculation_breakdown=dict(current.calculation_breakdown) if current else {},
            limitations=[
                LimitationView.of(item) for item in (current.limitations if current else [])
            ],
            next_actions=[
                NextActionView.of(item) for item in (current.next_actions if current else [])
            ],
            facts_used=[
                item for item in resolved if item.input_kind != LinkInputKind.TRAVEL_RECORD_VERSION
            ],
            travel_inputs=[
                item for item in resolved if item.input_kind == LinkInputKind.TRAVEL_RECORD_VERSION
            ],
            rule=RuleView.of(view.rule, view.guidance) if view.rule is not None else None,
            guidance=view.guidance,
            history=[ResultHistoryView.of(item) for item in view.history],
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


# --- case overview (Domain §44.1) -------------------------------------------


class GroupSummaryView(BaseModel):
    """One requirement group, compressed without losing what its members said.

    `conclusion_counts` is a tally by named state — never a fraction and never ordered as
    progress (CLAUDE.md §2.6). `not_yet_assessed` sits outside it so a group containing
    requirements nothing has decided can never read as complete. `currency` inherits the
    weakest member's (ADR-0010): one stale member makes the group stale.
    """

    group_key: str
    conclusion_counts: dict[str, int]
    not_yet_assessed: int
    total: int
    currency: str | None
    needs_attention: int
    stale: int
    is_fully_concluded: bool
    #: The group's requirements, in display order, so the overview can link to each.
    requirements: list[RequirementLink]

    @classmethod
    def of(cls, summary: GroupSummary, members: list[GroupMember]) -> "GroupSummaryView":
        return cls(
            group_key=summary.group_key,
            conclusion_counts=summary.conclusion_counts,
            not_yet_assessed=summary.not_yet_assessed,
            total=summary.total,
            currency=summary.currency,
            needs_attention=summary.needs_attention,
            stale=summary.stale,
            is_fully_concluded=summary.is_fully_concluded,
            requirements=[
                RequirementLink(
                    requirement_key=m.requirement_key,
                    title=m.title,
                    conclusion=m.conclusion,
                    currency=m.currency,
                )
                for m in members
                if m.group_key == summary.group_key
            ],
        )


class PriorityActionView(BaseModel):
    """One of the at-most-three actions the overview surfaces, with the requirement that
    raised it so the user can open the full explanation."""

    requirement_key: str
    requirement_title: str
    conclusion: str
    code: str
    parameters: dict[str, object]
    text: str | None
    blocking: bool

    @classmethod
    def of(cls, action: CandidateAction) -> "PriorityActionView":
        return cls(
            requirement_key=action.requirement_key,
            requirement_title=action.requirement_title,
            conclusion=action.conclusion,
            code=action.code,
            parameters=action.parameters,
            text=render_next_action(action.code, action.parameters),
            blocking=action.blocking,
        )


class CaseOverview(BaseModel):
    """The case overview read model (Domain §44.1).

    **`open_issue_count` and `evidence_coverage` are deliberately absent.** §44.1 lists
    both, but issue detection is M6 and evidence is M5. A zero here would say the system
    checked and found nothing, which is a stronger claim than the product can make. The
    fields arrive with the subsystems that populate them.
    """

    case_id: uuid.UUID
    title: str
    route_key: str
    lifecycle_status: str
    #: Derived from assessment state, never the stored column (ADR-0009).
    current_phase: str
    application_date: date | None
    groups: list[GroupSummaryView]
    priority_actions: list[PriorityActionView]
    #: How many actions exist beyond the three shown, so the cap never hides work silently.
    priority_actions_hidden: int
    #: Requirements with no real conclusion yet, across the whole case.
    not_yet_assessed: int
    #: Requirements whose displayed result is stale.
    stale: int
    total_requirements: int
    last_assessed_at: datetime | None

    @classmethod
    def from_view(cls, view: "CaseOverviewView") -> "CaseOverview":
        return cls(
            case_id=view.case.id,
            title=view.case.title,
            route_key=view.case.route_key,
            lifecycle_status=view.case.lifecycle_status.value,
            current_phase=view.phase.value,
            application_date=view.application_date,
            groups=[GroupSummaryView.of(group, view.members) for group in view.groups],
            priority_actions=[PriorityActionView.of(a) for a in view.actions.shown],
            priority_actions_hidden=view.actions.hidden,
            not_yet_assessed=sum(g.not_yet_assessed for g in view.groups),
            stale=sum(g.stale for g in view.groups),
            total_requirements=sum(g.total for g in view.groups),
            last_assessed_at=view.last_assessed_at,
        )
