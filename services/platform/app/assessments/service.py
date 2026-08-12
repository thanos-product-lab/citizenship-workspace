"""Assessment commands. Domain logic lives here, not in the route handlers.

Slice 1 command: `recalculate`. It gathers the case's current trusted inputs (the
confirmed route profile version and the selected application date version), runs the
in-scope evaluators, and writes an immutable `AssessmentRun` with its per-requirement
`AssessmentResult`s and exact `AssessmentInputLink`s — one atomic unit of work.

Immutability in practice: a re-run never edits a prior result. It marks the previous
current result SUPERSEDED (flushed *before* the replacement is inserted, so the
"one CURRENT per case + requirement" unique index is never momentarily violated) and
writes a new CURRENT result. The persisted result is the single source of truth for a
requirement's conclusion (ADR-0007); the read projection reads only from here.

`route_rules` stays the single evaluator — this module orchestrates and persists, and
reads the clock the rules never touch.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfileVersion
from app.applicants.repository import RouteProfileRepository
from app.assessments.domain import (
    AssessmentInputLink,
    AssessmentMode,
    AssessmentResult,
    AssessmentRun,
    AssessmentRunCompleted,
    AssessmentTriggerType,
)
from app.assessments.repository import AssessmentRepository, RequirementCatalogRepository
from app.auth.schemas import CurrentUser
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.requirements.evaluation import (
    EvaluatedResult,
    ResidenceAssessmentInputs,
    RouteAssessmentInputs,
    TripInput,
    evaluate_residence_requirements,
    evaluate_route_requirements,
)
from app.requirements.models import RequirementDefinition
from app.residence.domain import (
    DateConfidence,
    ProposedApplicationDateVersion,
    TravelReviewState,
)
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)
from app.shared.errors import CaseNotActive, CaseNotAssessable
from app.shared.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class RecalculationOutcome:
    run: AssessmentRun
    result_count: int
    requirements: list[tuple[RequirementDefinition, AssessmentResult | None]]


def recalculate(
    session: Session, *, case: ApplicationCase, user: CurrentUser
) -> RecalculationOutcome:
    """Run a trusted assessment over the case's current inputs and persist immutable
    results. Requires an active case with a selected application date."""
    if case.lifecycle_status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(case.lifecycle_status.value)

    profile_version = _current_route_profile_version(session, case.id)
    date_version = _current_application_date_version(session, case.id)

    route_inputs = RouteAssessmentInputs(
        date_of_birth=profile_version.date_of_birth,
        status_type=profile_version.status_type,
        married_to_british_citizen=profile_version.married_to_british_citizen,
        may_already_be_british=profile_version.may_already_be_british,
        application_date=date_version.application_date,
        route_profile_version_id=profile_version.id,
        application_date_version_id=date_version.id,
    )
    residence_inputs = ResidenceAssessmentInputs(
        application_date=date_version.application_date,
        application_date_version_id=date_version.id,
        trips=_gather_trips(session, case.id),
    )
    evaluated = [
        *evaluate_route_requirements(route_inputs),
        *evaluate_residence_requirements(residence_inputs),
    ]

    run = AssessmentRun.start(
        case_id=case.id,
        trigger_type=AssessmentTriggerType.USER_REQUESTED,
        mode=AssessmentMode.TRUSTED,
        initiated_by=user.user_id,
    )
    AssessmentRepository.add_run(session, run)
    session.flush()

    for evaluation in evaluated:
        _persist_result(session, case_id=case.id, run_id=run.id, evaluation=evaluation)

    run.complete(at=datetime.now(UTC))

    uow = UnitOfWork(session, actor_id=user.user_id)
    uow.emit(
        AssessmentRunCompleted(
            aggregate_id=run.id,
            trigger_type=run.trigger_type,
            mode=run.mode,
            result_count=len(evaluated),
        ),
        case_id=case.id,
        action="assessment.recalculated",
        target_type="AssessmentRun",
        target_id=run.id,
    )
    uow.commit()

    return RecalculationOutcome(
        run=run,
        result_count=len(evaluated),
        requirements=AssessmentRepository.list_requirements_with_current(session, case.id),
    )


def list_requirements(
    session: Session, *, case: ApplicationCase
) -> list[tuple[RequirementDefinition, AssessmentResult | None]]:
    """Every catalogued requirement with its current result (or None), in display order."""
    return AssessmentRepository.list_requirements_with_current(session, case.id)


@dataclass(frozen=True)
class RequirementDetailView:
    definition: RequirementDefinition
    current: AssessmentResult | None
    input_links: list[AssessmentInputLink]
    guidance: list[dict[str, str]]
    history: list[AssessmentResult]


def get_requirement_detail(
    session: Session, *, case: ApplicationCase, requirement_key: str
) -> RequirementDetailView | None:
    """The full detail for one requirement, or None if the key is not catalogued. Guidance
    comes from the current result's rule version, else the requirement's active one."""
    definition = RequirementCatalogRepository.get_definition_by_key(session, requirement_key)
    if definition is None:
        return None
    current = AssessmentRepository.get_current_for_requirement(session, case.id, definition.id)
    input_links = (
        AssessmentRepository.list_input_links(session, current.id) if current is not None else []
    )
    if current is not None:
        guidance = RequirementCatalogRepository.get_guidance(session, current.rule_version_id)
    else:
        active = RequirementCatalogRepository.get_active_rule_version(session, definition.id)
        guidance = (
            RequirementCatalogRepository.get_guidance(session, active.id)
            if active is not None
            else []
        )
    history = AssessmentRepository.list_history_for_requirement(session, case.id, definition.id)
    return RequirementDetailView(
        definition=definition,
        current=current,
        input_links=input_links,
        guidance=guidance,
        history=history,
    )


# --- helpers ---------------------------------------------------------------


def _persist_result(
    session: Session, *, case_id: uuid.UUID, run_id: uuid.UUID, evaluation: EvaluatedResult
) -> None:
    """Supersede any prior current result, then write the new current result and its exact
    input links. The supersession is flushed before the insert so the partial unique index
    (one CURRENT per case + requirement) is never violated mid-transaction."""
    definition = RequirementCatalogRepository.get_definition_by_key(
        session, evaluation.requirement_key
    )
    if definition is None:  # a seeded evaluator with no catalog row is a packaging bug
        raise RuntimeError(f"no requirement definition for {evaluation.requirement_key!r}")
    rule_version = RequirementCatalogRepository.get_active_rule_version(session, definition.id)
    if rule_version is None:
        raise RuntimeError(f"no active rule version for {evaluation.requirement_key!r}")

    result_id = uuid.uuid4()
    prior = AssessmentRepository.get_current_for_requirement(session, case_id, definition.id)
    if prior is not None:
        prior.supersede(by_result_id=result_id)
        session.flush()

    result = AssessmentResult.new_current(
        result_id=result_id,
        run_id=run_id,
        case_id=case_id,
        requirement_id=definition.id,
        rule_version_id=rule_version.id,
        conclusion=evaluation.conclusion,
        summary_code=evaluation.summary_code,
        summary_parameters=dict(evaluation.summary_parameters),
        calculation_breakdown=dict(evaluation.calculation_breakdown),
        limitations=[limitation.as_dict() for limitation in evaluation.limitations],
        next_actions=[action.as_dict() for action in evaluation.next_actions],
    )
    AssessmentRepository.add_result(session, result)
    session.flush()

    for link in evaluation.input_links:
        AssessmentRepository.add_input_link(
            session,
            AssessmentInputLink(
                assessment_result_id=result_id,
                input_kind=link.input_kind.value,
                input_version_id=link.input_version_id,
                input_key=link.input_key,
                contribution_role=link.contribution_role.value,
            ),
        )


def _gather_trips(session: Session, case_id: uuid.UUID) -> tuple[TripInput, ...]:
    """Every active travel record, flattened to primitives, with the §6.1 trust gate decided
    here (ACTIVE + CONFIRMED + EXACT). The evaluator gets all active trips — trusted totals
    use the gated subset, provisional totals use all — so the sensitivity rule can run."""
    records = TravelRecordRepository.list_active_with_current_version(session, case_id)
    return tuple(
        TripInput(
            departure_date=version.departure_date,
            return_date=version.return_date,
            travel_record_version_id=version.id,
            is_trusted=(
                version.review_state == TravelReviewState.CONFIRMED.value
                and version.date_confidence == DateConfidence.EXACT.value
            ),
        )
        for _record, version in records
    )


def _current_route_profile_version(session: Session, case_id: uuid.UUID) -> RouteProfileVersion:
    profile = RouteProfileRepository.get_for_case(session, case_id)
    version = (
        RouteProfileRepository.get_version(session, profile.current_version_id)
        if profile is not None and profile.current_version_id is not None
        else None
    )
    if version is None:  # an active case always has a confirmed profile version
        raise CaseNotAssessable("the case has no confirmed route profile")
    return version


def _current_application_date_version(
    session: Session, case_id: uuid.UUID
) -> ProposedApplicationDateVersion:
    root = ProposedApplicationDateRepository.get_current_for_case(session, case_id)
    version = (
        ProposedApplicationDateRepository.get_version(session, root.current_version_id)
        if root is not None and root.current_version_id is not None
        else None
    )
    if version is None:
        raise CaseNotAssessable("select an application date before running an assessment")
    return version
