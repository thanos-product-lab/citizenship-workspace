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
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import overload

import structlog
from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfileVersion
from app.applicants.repository import RouteProfileRepository
from app.assessments.domain import (
    AssessmentInputLink,
    AssessmentMode,
    AssessmentResult,
    AssessmentRun,
    AssessmentRunCompleted,
    AssessmentRunFailed,
    AssessmentTriggerType,
    RecalculationFailureCode,
)
from app.assessments.groups import GroupMember, GroupSummary, summarise_groups
from app.assessments.priority import CandidateAction, PriorityActions, select_priority_actions
from app.assessments.provenance import ResolvedInput, resolve_input_links
from app.assessments.repository import AssessmentRepository, RequirementCatalogRepository
from app.auth.schemas import CurrentUser
from app.cases import service as cases_service
from app.cases.domain import ApplicationCase, CasePhase, LifecycleStatus
from app.cases.phase import RequirementState, derive_phase
from app.evidence.repository import EvidenceLinkRepository
from app.issues import service as issues_service
from app.issues.repository import IssueRepository
from app.requirements.domain import Conclusion
from app.requirements.evaluation import (
    EvaluatedResult,
    EvidenceLinkInput,
    ResidenceAssessmentInputs,
    RouteAssessmentInputs,
    TripInput,
    UnlinkedResult,
    evaluate_residence_requirements,
    evaluate_route_requirements,
    evaluate_status_holding_period,
    without_provenance,
)
from app.requirements.models import RequirementDefinition, RuleVersion
from app.residence.domain import (
    ProposedApplicationDateVersion,
    counts_toward_trusted_total,
)
from app.residence.repository import (
    ProposedApplicationDateRepository,
    TravelRecordRepository,
)
from app.shared.db import get_sessionmaker
from app.shared.errors import CaseNotActive, CaseNotAssessable, DomainError
from app.shared.tenant import set_tenant
from app.shared.trace import current_trace_id
from app.shared.unit_of_work import UnitOfWork

_log = structlog.get_logger()


class RuleConfigurationMissing(RuntimeError):
    """A catalogued requirement has no definition row or no active rule version.

    A packaging bug, not a user error, so it stays a `RuntimeError` and reaches the client
    as a 500 — but it is distinguishable from an arbitrary failure, which is what lets the
    recorded run say `RULE_CONFIGURATION_INVALID` (retrying will fail identically) rather
    than `UNEXPECTED_ERROR` (retrying may well work).
    """


@dataclass(frozen=True)
class RecalculationOutcome:
    run: AssessmentRun
    result_count: int
    requirements: list[tuple[RequirementDefinition, AssessmentResult | None]]


def recalculate(
    session: Session, *, case: ApplicationCase, user: CurrentUser
) -> RecalculationOutcome:
    """Run a trusted assessment over the case's current inputs and persist immutable
    results. Requires an active case with a selected application date.

    **A failure leaves the case in its safe state and says so** (Domain §41.4). Nothing is
    promoted to CURRENT, the previous results stay exactly as they were — STALE, with the
    conclusion they already had — and a FAILED `AssessmentRun` is written in a *separate*
    transaction so the record survives the rollback that discards everything else. The
    queue then shows a `PROCESSING_FAILURE` item that outlives the page reload which erases
    a transient banner.

    The precondition failures above are deliberately outside that handling. A case that is
    not active, or has no application date, has not suffered a processing failure — the
    request was wrong, the case is fine, and recording a FAILED run for it would put an
    item in the queue that no retry can clear.
    """
    if case.lifecycle_status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(case.lifecycle_status.value)

    # Read the id out of the ORM object *before* anything can roll back. A rollback expires
    # every instance in the session, so touching `case.id` afterwards emits a refresh SELECT
    # — which autobegins a fresh transaction on the session we just discarded, leaving the
    # request holding a pooled connection idle-in-transaction for the whole recovery.
    case_id = case.id

    # Lock the case row before reading any input — the three residence write commands take
    # the same lock, so this serialises against them. Without it, under READ COMMITTED: this
    # run reads application-date v1; a concurrent date change writes v2, marks the results
    # STALE and commits; this run's supersede then retires that stale row and writes a new
    # CURRENT result derived from v1. The case ends with a current conclusion built on a
    # superseded input, nothing stale, and nothing failing — exactly the state selective
    # invalidation exists to make impossible.
    cases_service.lock_writable_case(session, case.id)

    try:
        run, result_count = _run_trusted_assessment(session, case=case, user=user)
    except DomainError:
        # A rule about the request, already mapped to a 4xx, so no failure is recorded.
        # `CaseNotActive` / `CaseNotAssessable`: the case is intact and the caller knows
        # what to do. `ConcurrencyConflict`: another writer holds the results this run
        # would have written — the recalculation it performed stands, and a retry is the
        # documented response to a 409. The exception is a unique violation raised from
        # the issue reconcile rather than from the result write, which `UnitOfWork`
        # cannot tell apart and maps here too; that is a genuine processing failure
        # reported as a conflict. Harmless — the results stay STALE and the 409 says
        # retry — but it is the one case this clause is wrong about.
        raise
    except Exception as exc:
        # Stamp the failure *now*, not when the recovery session eventually opens.
        # `_abandon` releases the case lock on the next line, so a concurrent
        # recalculation can complete and commit in the gap — and if the recovery then
        # dated itself later, it would sort after that success and raise a processing
        # failure on a case whose every result is CURRENT. The gap is not small: the
        # recovery has to check out a pooled connection, and an exhausted pool is a
        # leading cause of the failure being recorded in the first place.
        failed_at = datetime.now(UTC)
        _abandon(session)
        _record_failed_run(case_id=case_id, user=user, failure_code=_classify(exc), at=failed_at)
        raise

    return RecalculationOutcome(
        run=run,
        result_count=result_count,
        requirements=AssessmentRepository.list_requirements_with_active_result(session, case_id),
    )


@dataclass(frozen=True)
class TrustedEvaluation:
    """Evaluated at the case's own current application date. Carries provenance, so these
    results — and only these — can be persisted."""

    application_date: date
    results: list[EvaluatedResult]


@dataclass(frozen=True)
class OverriddenEvaluation:
    """Evaluated at a candidate application date the case does not hold. No versioned
    input carries that date, so the results have no provenance and no field for any."""

    application_date: date
    results: list[UnlinkedResult]


Evaluation = TrustedEvaluation | OverriddenEvaluation


@overload
def evaluate_case(session: Session, *, case: ApplicationCase) -> TrustedEvaluation: ...


@overload
def evaluate_case(
    session: Session, *, case: ApplicationCase, application_date_override: None
) -> TrustedEvaluation: ...


@overload
def evaluate_case(
    session: Session, *, case: ApplicationCase, application_date_override: date
) -> OverriddenEvaluation: ...


def evaluate_case(
    session: Session, *, case: ApplicationCase, application_date_override: date | None = None
) -> Evaluation:
    """Read the case's current inputs and run every in-scope evaluator over them.

    **Read-only.** Only SELECTs: the confirmed route profile version, the selected
    application date version, and every active travel record. Nothing is added to the
    session, nothing is flushed, no unit of work is constructed. That is what lets the
    simulation path call it (Domain §10.3: previewing a date must not change the case).

    `application_date_override` substitutes the date the rules measure against — the whole
    of what a date simulation changes. Everything else is read from the case exactly as a
    trusted run reads it, which is the point: both paths call this one function, so the
    arithmetic cannot fork. `tests/assessments/test_simulation.py` pins that by simulating
    the case's own current date and requiring the results to match the persisted ones
    field for field.

    The return type is a closed union rather than a flag, and the overloads above narrow it
    per call site: omit the override and you get `TrustedEvaluation`, pass one and you get
    `OverriddenEvaluation`, whose results have no `input_links` field at all. So
    `_persist_result` cannot be handed a simulated result — a type error at `just typecheck`,
    with no `isinstance` guard for anyone to delete. See `without_provenance`.
    """
    profile_version = _current_route_profile_version(session, case.id)
    date_version = _current_application_date_version(session, case.id)
    application_date = application_date_override or date_version.application_date

    route_inputs = RouteAssessmentInputs(
        date_of_birth=profile_version.date_of_birth,
        status_type=profile_version.status_type,
        status_granted_on=profile_version.status_granted_on,
        married_to_british_citizen=profile_version.married_to_british_citizen,
        may_already_be_british=profile_version.may_already_be_british,
        application_date=application_date,
        route_profile_version_id=profile_version.id,
        application_date_version_id=date_version.id,
    )
    residence_inputs = ResidenceAssessmentInputs(
        application_date=application_date,
        application_date_version_id=date_version.id,
        trips=_gather_trips(session, case.id),
        evidence_links=_gather_evidence_links(session, case.id),
    )
    evaluated = [
        *evaluate_route_requirements(route_inputs),
        evaluate_status_holding_period(route_inputs),
        *evaluate_residence_requirements(residence_inputs),
    ]

    if application_date_override is None:
        return TrustedEvaluation(application_date=application_date, results=evaluated)
    # The version ids above are real — the profile and travel versions genuinely were read.
    # The application-date version was not: its date is not the date these conclusions were
    # drawn at. Rather than link a subset and leave the rule's declared dependencies
    # half-satisfied, the whole link set goes.
    return OverriddenEvaluation(
        application_date=application_date,
        results=[without_provenance(result) for result in evaluated],
    )


def _run_trusted_assessment(
    session: Session, *, case: ApplicationCase, user: CurrentUser
) -> tuple[AssessmentRun, int]:
    """Evaluate, persist, and commit. Everything that can fail on the happy path lives
    here, so the caller's `except` covers exactly the work whose failure is worth
    recording — and nothing after the commit, where a failure would mean the run
    succeeded and a FAILED row would be a lie."""
    evaluated = evaluate_case(session, case=case).results

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
    # Same unit of work as the run: the results and the issues describing them commit
    # together. This is what auto-resolves the STALE_ASSESSMENT issues the change opened —
    # not a special case in the recalculation path, just the reconciler finding those
    # causes gone.
    issues_service.reconcile(session, uow, case_id=case.id)
    uow.commit()
    return run, len(evaluated)


def _classify(exc: BaseException) -> RecalculationFailureCode:
    """The exception *type* decides the code. The message never does — see
    `RecalculationFailureCode`."""
    if isinstance(exc, RuleConfigurationMissing):
        return RecalculationFailureCode.RULE_CONFIGURATION_INVALID
    return RecalculationFailureCode.UNEXPECTED_ERROR


def _abandon(session: Session) -> None:
    """Discard the failed transaction before opening the recovery one.

    Two reasons. It releases the `FOR UPDATE` lock this command took on the case row, which
    the recovery transaction would otherwise be waiting behind — and it discards the
    partial results, which is what makes "nothing is promoted to CURRENT" true rather than
    merely intended. Best-effort like everything else on this path: if the connection is
    the thing that broke, there is nothing to roll back and nothing to gain by saying so.
    """
    try:
        session.rollback()
    except Exception:  # pragma: no cover - only reachable with a dead connection
        _log.warning("assessment.rollback_failed", trace_id=current_trace_id())


def _record_failed_run(
    *,
    case_id: uuid.UUID,
    user: CurrentUser,
    failure_code: RecalculationFailureCode,
    at: datetime,
) -> None:
    """Write the durable record of a failed recalculation, in its own session and
    transaction (Domain §41.4).

    **This must never raise.** It runs from inside an `except` block, and an exception
    thrown out of a handler replaces the original one: the engineer investigating would be
    shown the recovery's failure and lose the actual cause on the way out. Worse, the most
    likely reason this write fails is that the *database connection* is what broke the
    recalculation in the first place — so the one failure mode that guarantees the recovery
    also fails is the one where the original error matters most.

    So the durable record is an improvement on the safe state, not a precondition for it.
    The results are already STALE and nothing was promoted; if this write is lost the user
    sees stale conclusions without the explanation, which is worse than the alternative but
    still not misleading.

    The recovery's own exception is logged by type and trace id, not by message. A driver
    error carries the failing statement's bound parameters, and this line is not the place
    to discover that a destination label reached the log (§11).
    """
    try:
        with get_sessionmaker()() as session:
            # A fresh session starts outside the RLS context, so the tenant has to be set
            # again — otherwise the policies see a NULL user id, match no row, and the
            # insert is rejected. Fail-closed working exactly as designed, on a path where
            # it would look like an inexplicable recovery failure.
            set_tenant(session, user.user_id)
            run = AssessmentRun.start(
                case_id=case_id,
                trigger_type=AssessmentTriggerType.USER_REQUESTED,
                mode=AssessmentMode.TRUSTED,
                initiated_by=user.user_id,
            )
            # `at` is the instant the recalculation failed, passed in by the caller.
            # Reading the clock here instead would date the failure after any run that
            # succeeded while this one was waiting for a connection.
            run.fail(code=failure_code, at=at, trace_id=current_trace_id())
            AssessmentRepository.add_run(session, run)
            uow = UnitOfWork(session, actor_id=user.user_id)
            uow.emit(
                AssessmentRunFailed(
                    aggregate_id=run.id,
                    trigger_type=run.trigger_type,
                    mode=run.mode,
                    failure_code=failure_code.value,
                ),
                case_id=case_id,
                action="assessment.failed",
                target_type="AssessmentRun",
                target_id=run.id,
            )
            # The issue is not created here. Reconciliation derives PROCESSING_FAILURE from
            # this run being the latest and having failed, so the same diff that opens it
            # closes it when a later run succeeds — no cleanup to remember on a path added
            # months from now.
            issues_service.reconcile(session, uow, case_id=case_id)
            uow.commit()
    except Exception as exc:
        _log.error(
            "assessment.failure_record_failed",
            case_id=str(case_id),
            failure_code=failure_code.value,
            error_type=type(exc).__name__,
            trace_id=current_trace_id(),
        )


def list_requirements(
    session: Session, *, case: ApplicationCase
) -> list[tuple[RequirementDefinition, AssessmentResult | None]]:
    """Every catalogued requirement with its current result (or None), in display order."""
    return AssessmentRepository.list_requirements_with_active_result(session, case.id)


def derive_phases(
    session: Session, *, cases: Sequence[ApplicationCase]
) -> dict[uuid.UUID, CasePhase]:
    """Each case's phase, derived from its current assessment state (Domain §7.5, ADR-0009).

    This module does the gathering because it is the one that already reads both the case
    aggregate and the requirements catalogue; `cases.phase` owns the rule itself and stays
    a pure function. The stored `cases.current_phase` column is never consulted — it is
    written once at creation and never advanced, so it reports SETTING_UP forever.

    Only ACTIVE cases need assessment state, so a list of draft cases costs no query at all.
    """
    active_ids = [c.id for c in cases if c.lifecycle_status is LifecycleStatus.ACTIVE]
    states_by_case = (
        AssessmentRepository.list_displayed_states_by_case(session, active_ids)
        if active_ids
        else {}
    )
    catalogue_size = RequirementCatalogRepository.count_definitions(session) if active_ids else 0
    return {
        case.id: derive_phase(
            lifecycle_status=case.lifecycle_status,
            states=[
                RequirementState(conclusion=conclusion, currency=currency)
                for conclusion, currency in states_by_case.get(case.id, [])
            ],
            catalogue_size=catalogue_size,
        )
        for case in cases
    }


def derive_case_phase(session: Session, *, case: ApplicationCase) -> CasePhase:
    """The phase for a single case. Convenience over `derive_phases`."""
    return derive_phases(session, cases=[case])[case.id]


@dataclass(frozen=True)
class CaseOverviewView:
    """Everything the overview screen reads, gathered once (Domain §44.1).

    `open_issue_count` joins here now that issues exist: a zero is a real statement that the
    system looked and found nothing, which it could not honestly make before. **Evidence
    coverage is still absent** for the same reason it was — there is no evidence subsystem
    until M7, and a zero would claim a check nobody ran.
    """

    case: ApplicationCase
    phase: CasePhase
    application_date: date | None
    groups: list[GroupSummary]
    #: Every requirement with its group, so the overview can list and link them.
    members: list[GroupMember]
    #: Issues awaiting the user: OPEN or IN_PROGRESS, dismissed ones excluded.
    open_issue_count: int
    actions: PriorityActions
    last_assessed_at: datetime | None


def get_case_overview(session: Session, *, case: ApplicationCase) -> CaseOverviewView:
    """The case overview projection. One pass over the requirement catalogue and its
    displayed results; the group and priority rules are pure functions over that."""
    projection = AssessmentRepository.list_requirements_with_active_result(session, case.id)

    members: list[GroupMember] = []
    candidates: list[CandidateAction] = []
    last_assessed: datetime | None = None

    for definition, result in projection:
        conclusion = result.conclusion if result else Conclusion.NOT_YET_ASSESSED.value
        members.append(
            GroupMember(
                requirement_key=definition.requirement_key,
                group_key=definition.group_key,
                title=definition.title,
                conclusion=conclusion,
                currency=result.currency if result else None,
                display_order=definition.display_order,
            )
        )
        if result is None:
            continue
        if last_assessed is None or result.created_at > last_assessed:
            last_assessed = result.created_at
        for raw in result.next_actions:
            raw_priority = raw.get("priority")
            candidates.append(
                CandidateAction(
                    requirement_key=definition.requirement_key,
                    requirement_title=definition.title,
                    conclusion=conclusion,
                    currency=result.currency,
                    display_order=definition.display_order,
                    code=str(raw.get("code", "")),
                    parameters=dict(raw.get("label_parameters") or {}),
                    priority=raw_priority if isinstance(raw_priority, int) else 0,
                    blocking=bool(raw.get("blocking", False)),
                )
            )

    date_version = _current_application_date_version_or_none(session, case.id)

    return CaseOverviewView(
        case=case,
        phase=derive_case_phase(session, case=case),
        application_date=date_version.application_date if date_version else None,
        groups=summarise_groups(members),
        members=members,
        open_issue_count=IssueRepository.count_open(session, case.id),
        actions=select_priority_actions(candidates),
        last_assessed_at=last_assessed,
    )


def _current_application_date_version_or_none(
    session: Session, case_id: uuid.UUID
) -> ProposedApplicationDateVersion | None:
    """The selected date, or None. Unlike `_current_application_date_version` this does not
    raise: the overview must render for a case that has not chosen a date yet."""
    root = ProposedApplicationDateRepository.get_current_for_case(session, case_id)
    if root is None or root.current_version_id is None:
        return None
    return ProposedApplicationDateRepository.get_version(session, root.current_version_id)


@dataclass(frozen=True)
class RequirementDetailView:
    definition: RequirementDefinition
    current: AssessmentResult | None
    #: Input links resolved against the versions they point at, so the detail screen can
    #: show what was read rather than a list of UUIDs.
    inputs: list[ResolvedInput]
    #: The rule version the *displayed result* ran under — not the requirement's currently
    #: active rule, which may since have moved on.
    rule: RuleVersion | None
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
    # The displayed result is the non-superseded one — CURRENT, or STALE after an input change.
    current = AssessmentRepository.get_supersedable_for_requirement(session, case.id, definition.id)

    if current is not None:
        links = AssessmentRepository.list_input_links(session, current.id)
        inputs = resolve_input_links(session, links)
        rule = RequirementCatalogRepository.get_rule_version(session, current.rule_version_id)
    else:
        # No result yet: there are no inputs to show, but the requirement still has a rule
        # and a guidance citation, so the reader can see what *would* be applied.
        inputs = []
        rule = RequirementCatalogRepository.get_active_rule_version(session, definition.id)

    guidance = (
        RequirementCatalogRepository.get_guidance(session, rule.id) if rule is not None else []
    )
    history = AssessmentRepository.list_history_for_requirement(session, case.id, definition.id)
    return RequirementDetailView(
        definition=definition,
        current=current,
        inputs=inputs,
        rule=rule,
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
        raise RuleConfigurationMissing(
            f"no requirement definition for {evaluation.requirement_key!r}"
        )
    rule_version = RequirementCatalogRepository.get_active_rule_version(session, definition.id)
    if rule_version is None:
        raise RuleConfigurationMissing(f"no active rule version for {evaluation.requirement_key!r}")

    result_id = uuid.uuid4()
    # Supersede the prior non-superseded result whether it is CURRENT or STALE — a recalc after
    # an input change must retire the stale result, not leave it beside the new current one.
    prior = AssessmentRepository.get_supersedable_for_requirement(session, case_id, definition.id)
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
            travel_record_id=record.id,
            is_trusted=counts_toward_trusted_total(record, version),
            date_confidence=version.date_confidence,
            review_state=version.review_state,
        )
        for record, version in records
    )


def _gather_evidence_links(session: Session, case_id: uuid.UUID) -> tuple[EvidenceLinkInput, ...]:
    """Every link currently counting as coverage, flattened to two ids.

    Two ids, because that is all the rule is allowed to see. Passing the `EvidenceItem`
    would let a later change read its category or its extracted text and turn coverage
    into a judgement about whether the document fits — which needs a model and is M8's
    (ADR-0021). The narrow shape is the enforcement.
    """
    return tuple(
        EvidenceLinkInput(link_id=link.id, travel_record_id=link.travel_record_id)
        for link in EvidenceLinkRepository.live_for_case(session, case_id=case_id)
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


def current_application_date(session: Session, case_id: uuid.UUID) -> date:
    """The case's selected application date. Raises `CaseNotAssessable` if none is set.

    Exists so a caller that needs only the date does not have to evaluate the whole case to
    get it — which the simulation did, discarding nine results to read one field and leaving
    a `TrustedEvaluation` in scope beside the overridden one. `EvaluatedResult` is a subtype
    of `UnlinkedResult`, so swapping which of the two the response was built from would have
    type-checked clean and rendered a trusted evaluation as a preview.
    """
    return _current_application_date_version(session, case_id).application_date


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
