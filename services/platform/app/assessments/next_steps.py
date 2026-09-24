"""The case's next step: one answer to "what now", derived from where the case stands.

A returning user could not tell where they had left off. The overview answered "what now"
at two moments only (a static Start here list before any assessment, and the requirements'
own next actions after one), while the rest of what they needed was spread over four
screens: stale conclusions in the header, documents waiting on Evidence, things to do on
Issues, trips with no document under "for your awareness". ADR-0034.

**Rules, not a model.** Each step is a plain condition on the case's state, checked in a
fixed order. Nothing here predicts, advises or scores (CLAUDE.md §1, §2.2, §2.6); it is
navigation over facts the case already holds.

**Derived at read time, never stored**, like the case phase (ADR-0009) and the passed-date
notice (ADR-0032): it is true whenever anyone looks, and cannot go out of date.

**Pure.** No session and no clock: `get_case_overview` gathers the inputs, so every rule
here is testable from a snapshot.

**Distinct from a result's `next_actions`.** Those are a requirement's own asks, emitted by
its rule and stored on the result. These are the case's steps. One of them,
`RESOLVE_REQUIREMENTS`, points at the next actions rather than repeating them.

**Never "you are ready".** When nothing is left the step says what this workspace cannot
check, because a green-looking finish line is the false reassurance the product exists to
prevent (CLAUDE.md §2.7).
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

#: The overview shows at most this many steps, the first of them as the primary one.
MAX_STEPS = 3


class StepCode(StrEnum):
    SET_APPLICATION_DATE = "SET_APPLICATION_DATE"
    ADD_TRIPS = "ADD_TRIPS"
    REVIEW_DOCUMENTS = "REVIEW_DOCUMENTS"
    RUN_ASSESSMENT = "RUN_ASSESSMENT"
    UPDATE_ASSESSMENT = "UPDATE_ASSESSMENT"
    RESOLVE_REQUIREMENTS = "RESOLVE_REQUIREMENTS"
    OPEN_ISSUES = "OPEN_ISSUES"
    ATTACH_TRIP_EVIDENCE = "ATTACH_TRIP_EVIDENCE"
    NOTHING_LEFT = "NOTHING_LEFT"


class DoneCode(StrEnum):
    DATE_SET = "DATE_SET"
    TRIPS_RECORDED = "TRIPS_RECORDED"
    ASSESSED = "ASSESSED"


class Destination(StrEnum):
    """Where a step's link goes, named rather than as a URL so the backend never owns the
    frontend's routes. The client maps each to a path."""

    CASE_DATA = "CASE_DATA"
    EVIDENCE = "EVIDENCE"
    REQUIREMENTS = "REQUIREMENTS"
    ISSUES = "ISSUES"
    PRIORITY_ACTIONS = "PRIORITY_ACTIONS"


@dataclass(frozen=True)
class NextStepInputs:
    """Everything the rules read, gathered once by `get_case_overview`."""

    application_date: date | None
    trip_count: int
    documents_awaiting_review: int
    #: At least one requirement has a result.
    assessed: bool
    last_assessed_on: date | None
    #: Displayed results whose currency is STALE.
    stale_count: int
    #: Requirement next actions the overview's priority cards would show.
    priority_action_count: int
    #: Open issue actions other than rechecks (ADR-0033), which `UPDATE_ASSESSMENT` covers.
    issue_actions_excluding_recheck: int
    trips_without_document: int


@dataclass(frozen=True)
class Step:
    code: StepCode
    destination: Destination
    parameters: dict[str, object] = field(default_factory=dict)
    #: Worth doing, and not required by anything the workspace checks.
    optional: bool = False


@dataclass(frozen=True)
class Done:
    code: DoneCode
    parameters: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NextSteps:
    done: list[Done]
    #: The first is the primary step. Never empty: `NOTHING_LEFT` when nothing applies.
    steps: list[Step]


def derive_next_steps(inputs: NextStepInputs) -> NextSteps:
    """The steps that apply, in order, capped at `MAX_STEPS`, plus what is already done."""
    candidates: list[Step] = []

    if inputs.application_date is None:
        # First, because every residence check is measured backwards from it: trips entered
        # before there is a date have no window to be counted against.
        candidates.append(Step(StepCode.SET_APPLICATION_DATE, Destination.CASE_DATA))

    if inputs.trip_count == 0 and not inputs.assessed:
        # Only before the first assessment. "No trips" is ambiguous (not entered yet, or
        # genuinely none), and once a case is assessed its totals already say zero, so a
        # permanent nag would ask someone who never left the UK to do something forever.
        candidates.append(Step(StepCode.ADD_TRIPS, Destination.CASE_DATA))

    if inputs.documents_awaiting_review > 0:
        candidates.append(
            Step(
                StepCode.REVIEW_DOCUMENTS,
                Destination.EVIDENCE,
                {"count": inputs.documents_awaiting_review},
            )
        )

    if inputs.application_date is not None and not inputs.assessed:
        candidates.append(Step(StepCode.RUN_ASSESSMENT, Destination.REQUIREMENTS))

    if inputs.assessed and inputs.stale_count > 0:
        candidates.append(
            Step(StepCode.UPDATE_ASSESSMENT, Destination.ISSUES, {"count": inputs.stale_count})
        )

    if inputs.priority_action_count > 0:
        candidates.append(
            Step(
                StepCode.RESOLVE_REQUIREMENTS,
                Destination.PRIORITY_ACTIONS,
                {"count": inputs.priority_action_count},
            )
        )

    if inputs.issue_actions_excluding_recheck > 0:
        candidates.append(
            Step(
                StepCode.OPEN_ISSUES,
                Destination.ISSUES,
                {"count": inputs.issue_actions_excluding_recheck},
            )
        )

    if inputs.trips_without_document > 0:
        candidates.append(
            Step(
                StepCode.ATTACH_TRIP_EVIDENCE,
                Destination.CASE_DATA,
                {"count": inputs.trips_without_document},
                optional=True,
            )
        )

    required = [step for step in candidates if not step.optional]
    if not required:
        # Nothing the workspace checks is outstanding. Said as a limit of the workspace,
        # never as readiness, and linked to Requirements, where what it has not assessed is
        # listed. An optional step, if any, still follows it.
        candidates.insert(0, Step(StepCode.NOTHING_LEFT, Destination.REQUIREMENTS))

    return NextSteps(done=_done(inputs), steps=candidates[:MAX_STEPS])


def _done(inputs: NextStepInputs) -> list[Done]:
    done: list[Done] = []
    if inputs.application_date is not None:
        done.append(Done(DoneCode.DATE_SET, {"date": inputs.application_date.isoformat()}))
    if inputs.trip_count > 0:
        done.append(Done(DoneCode.TRIPS_RECORDED, {"count": inputs.trip_count}))
    if inputs.assessed and inputs.last_assessed_on is not None:
        done.append(Done(DoneCode.ASSESSED, {"date": inputs.last_assessed_on.isoformat()}))
    return done
