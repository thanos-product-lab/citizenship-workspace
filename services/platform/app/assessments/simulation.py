"""Application-date simulation — the `ApplicationDateSimulationService` of Domain §48.3.

*"Calculates provisional effects of a candidate application date without mutating the
case."* The whole module is that sentence, and the interesting work is in what it does
**not** do.

A simulation reads the case's current inputs, runs the same evaluators a trusted run runs
with one substitution — the date the rules measure against — and returns the comparison.
It constructs no `AssessmentRun`, no `AssessmentResult`, no `AssessmentInputLink`, and no
`UnitOfWork`. It never reaches `invalidate_for_input_change`, so it never marks a result
stale and never triggers issue reconciliation (the only three call sites of
`issues_service.reconcile` are all on write paths this module does not touch). Nothing is
added to the session; the transaction it runs in has nothing to commit.

That is the Domain §10.3 invariant stated as an implementation: *"Previewing another date
does not change the case or mark assessments stale."*

**Why a provisional figure cannot be rendered as current** (Domain §42.2). Three layers,
strongest first:

1. No row exists. The only path that creates an `AssessmentResult` is
   `AssessmentResult.new_current()`, which hard-codes `currency = CURRENT`. Nothing here
   calls it, so there is no artefact for any projection to return.
2. No provenance exists to lie with. `evaluate_case(..., application_date_override=...)`
   returns `UnlinkedResult`s, which have no `input_links` field — persisting one is a type
   error (`app/requirements/evaluation.py`).
3. The wire type is different. `SimulatedRequirement` is not `RequirementSummary`: it has
   no run id, no result id, and its `after` side's `currency` is a `Literal["PROVISIONAL"]`
   with no code path by which it could be `"CURRENT"`.

**Why the numbers cannot drift from a real save.** Both paths call `evaluate_case`. That
is structural, and `tests/assessments/test_simulation.py` pins it anyway by simulating the
case's own current date and requiring every field to match the persisted results.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentResult
from app.assessments.repository import AssessmentRepository
from app.assessments.service import evaluate_case
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.requirements.evaluation import UnlinkedResult
from app.requirements.models import RequirementDefinition
from app.requirements.rules_core import (
    Window,
    final_year_window,
    physical_presence_date,
    qualifying_window,
)
from app.shared.errors import CaseNotActive

#: The summary parameter the presence rule publishes when it finds a later date whose
#: anchor is clear (RULES_SPEC §7.5). Lifted to the top of the response because it is the
#: one value that turns a refusal into an action.
RESOLVING_DATE_PARAMETER = "resolving_application_date"


@dataclass(frozen=True)
class SimulatedWindows:
    """The three date boundaries a candidate date moves, derived from `rules_core` rather
    than read back out of a rule's breakdown — one owner for the arithmetic either way, but
    this does not depend on which rule happened to publish which key."""

    qualifying_period: Window
    final_year: Window
    presence_anchor: date


@dataclass(frozen=True)
class SimulatedRequirement:
    definition: RequirementDefinition
    before_conclusion: str
    before_currency: str | None
    before_summary_code: str | None
    before_summary_parameters: dict[str, object]
    after: UnlinkedResult


@dataclass(frozen=True)
class SimulationView:
    current_application_date: date
    candidate_application_date: date
    windows_before: SimulatedWindows
    windows_after: SimulatedWindows
    resolving_application_date: date | None
    requirements: list[SimulatedRequirement]


def _windows(application_date: date) -> SimulatedWindows:
    return SimulatedWindows(
        qualifying_period=qualifying_window(application_date),
        final_year=final_year_window(application_date),
        presence_anchor=physical_presence_date(application_date),
    )


def _resolving_date(results: list[UnlinkedResult]) -> date | None:
    """The nearest later application date the presence rule found clear, if it looked.

    Read off whichever result publishes it rather than recomputed here: the forward search
    is the rule's, and duplicating its horizon or its trust gate in this module is exactly
    the fork the single-evaluator design exists to prevent.
    """
    for result in results:
        raw = result.summary_parameters.get(RESOLVING_DATE_PARAMETER)
        if isinstance(raw, str):
            return date.fromisoformat(raw)
        if isinstance(raw, date):
            return raw
    return None


def simulate_application_date(
    session: Session, *, case: ApplicationCase, candidate_date: date
) -> SimulationView:
    """Compare the case as it stands against the case evaluated at `candidate_date`.

    The "before" side is read from the persisted results, conclusion *and* currency, so a
    stale conclusion is shown as the stale conclusion it is rather than silently recomputed
    into something the case never concluded. The "after" side is evaluated live.

    Only the requirements the evaluators actually cover appear. Returning an untouched
    `NOT_YET_ASSESSED` for the referee slots beside a real residence change would imply the
    date moved something it cannot; `tests/assessments/test_simulation.py` asserts the set
    covers everything an application-date change would invalidate, which is the property
    that matters.

    Raises `CaseNotActive` for a case still onboarding, and `CaseNotAssessable` (from
    `evaluate_case`) when no application date has been selected — there is no "before" side
    to compare against, so the honest answer is a 409 rather than half a comparison.
    """
    if case.lifecycle_status is not LifecycleStatus.ACTIVE:
        raise CaseNotActive(case.lifecycle_status.value)

    trusted = evaluate_case(session, case=case)
    overridden = evaluate_case(session, case=case, application_date_override=candidate_date)

    after_by_key = {result.requirement_key: result for result in overridden.results}
    persisted = {
        definition.requirement_key: (definition, result)
        for definition, result in AssessmentRepository.list_requirements_with_active_result(
            session, case.id
        )
    }

    requirements = [
        _compare(persisted[key], after)
        for key, after in after_by_key.items()
        if key in persisted  # a catalogued requirement is always present; be explicit
    ]
    requirements.sort(key=lambda row: row.definition.display_order)

    return SimulationView(
        current_application_date=trusted.application_date,
        candidate_application_date=candidate_date,
        windows_before=_windows(trusted.application_date),
        windows_after=_windows(candidate_date),
        resolving_application_date=_resolving_date(overridden.results),
        requirements=requirements,
    )


def _compare(
    persisted: tuple[RequirementDefinition, AssessmentResult | None], after: UnlinkedResult
) -> SimulatedRequirement:
    definition, result = persisted
    if result is None:
        # Never assessed: the "before" side is the absence of a conclusion, not a
        # conclusion of absence. `NOT_YET_ASSESSED` with no currency says exactly that.
        return SimulatedRequirement(
            definition=definition,
            before_conclusion="NOT_YET_ASSESSED",
            before_currency=None,
            before_summary_code=None,
            before_summary_parameters={},
            after=after,
        )
    return SimulatedRequirement(
        definition=definition,
        before_conclusion=result.conclusion,
        before_currency=result.currency,
        before_summary_code=result.summary_code,
        before_summary_parameters=dict(result.summary_parameters or {}),
        after=after,
    )


__all__ = [
    "SimulatedRequirement",
    "SimulatedWindows",
    "SimulationView",
    "simulate_application_date",
]
