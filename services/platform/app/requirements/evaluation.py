"""The evaluation contract and the route-scope evaluator.

An evaluator is a **pure function of primitive inputs → `EvaluatedResult`s**. It reads
no ORM objects and touches no I/O — the assessment service gathers the current versioned
inputs, flattens them to primitives plus their version ids, and hands them here. Keeping
this module free of SQLAlchemy and of other modules' domain types is what lets the rules
stay reproducible and independently testable (as `route_rules` already is).

`route_rules` remains the single *evaluator* for route support; this module only shapes
its outcomes into persisted-result records and declares the exact input links each result
read. The assessment layer is the single *result store* (ADR-0007): it consumes these
records and writes `AssessmentResult` rows — nothing else records a route conclusion.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from app.requirements.route_rules import (
    KEY_ADULT,
    KEY_STANDARD,
    KEY_STATUS,
    evaluate_route_support,
)

# Requirement keys whose evaluators exist in this slice. GET /requirements reports every
# catalogued requirement; those not in this set have no trusted result yet and read as
# NOT_YET_ASSESSED. Residence and status keys join as their evaluators land.
ROUTE_REQUIREMENT_KEYS: tuple[str, ...] = (KEY_ADULT, KEY_STATUS, KEY_STANDARD)
IN_SCOPE_REQUIREMENT_KEYS: frozenset[str] = frozenset(ROUTE_REQUIREMENT_KEYS)


class LinkInputKind(StrEnum):
    """The versioned-input kinds an `AssessmentInputLink` can point at (Domain §31.1).
    Distinct from a rule's *dependency* kind (`DependencyInputKind`): a dependency names
    an input class (ROUTE_PROFILE); a link names the concrete version read
    (ROUTE_PROFILE_VERSION)."""

    ROUTE_PROFILE_VERSION = "ROUTE_PROFILE_VERSION"
    APPLICATION_DATE_VERSION = "APPLICATION_DATE_VERSION"
    TRAVEL_RECORD_VERSION = "TRAVEL_RECORD_VERSION"


class ContributionRole(StrEnum):
    REQUIRED = "REQUIRED"
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    LIMITING = "LIMITING"
    CONTEXTUAL = "CONTEXTUAL"


@dataclass(frozen=True)
class InputLinkSpec:
    """One versioned input a result actually read, to be persisted as an
    `AssessmentInputLink`. The set of these per result must equal the rule's declared
    dependencies (strict provenance): reading an undeclared input, or declaring one the
    evaluator never reads, is a defect the provenance test catches."""

    input_kind: LinkInputKind
    input_version_id: uuid.UUID
    input_key: str | None = None
    contribution_role: ContributionRole = ContributionRole.REQUIRED


@dataclass(frozen=True)
class EvaluatedResult:
    requirement_key: str
    conclusion: str
    summary_code: str | None
    summary_parameters: dict[str, object] = field(default_factory=dict)
    calculation_breakdown: dict[str, object] = field(default_factory=dict)
    input_links: tuple[InputLinkSpec, ...] = ()


@dataclass(frozen=True)
class RouteAssessmentInputs:
    """The flattened, primitive inputs the route-scope rules read, plus the ids of the
    versions they came from so the results can link exact provenance. The application
    date is the reference date the age check is evaluated at — a trusted run has one
    (recalculation requires a selected date), so it is not optional here."""

    date_of_birth: date | None
    status_type: str | None
    married_to_british_citizen: bool | None
    may_already_be_british: bool | None
    application_date: date
    route_profile_version_id: uuid.UUID
    application_date_version_id: uuid.UUID
    profile_confirmed: bool = True


def evaluate_route_requirements(inputs: RouteAssessmentInputs) -> list[EvaluatedResult]:
    """Evaluate the three route-scope rules and shape them into result records with exact
    input links. The age check uses the selected application date as its reference (not
    the wall clock), so the persisted result is anchored to a versioned input."""
    decision = evaluate_route_support(
        date_of_birth=inputs.date_of_birth,
        status_type=inputs.status_type,
        married_to_british_citizen=inputs.married_to_british_citizen,
        may_already_be_british=inputs.may_already_be_british,
        reference_date=inputs.application_date,
        profile_confirmed=inputs.profile_confirmed,
    )

    profile_link = InputLinkSpec(
        LinkInputKind.ROUTE_PROFILE_VERSION, inputs.route_profile_version_id
    )
    date_link = InputLinkSpec(
        LinkInputKind.APPLICATION_DATE_VERSION, inputs.application_date_version_id
    )
    reference: dict[str, object] = {"reference_date": inputs.application_date.isoformat()}

    # Per-result links mirror the seeded dependency rows (0007): adult reads DOB + the
    # application date; supported_status reads the status type; the composite reads the
    # profile answers, and its dependence on the adult/status conclusions is composition,
    # not an input link.
    return [
        EvaluatedResult(
            requirement_key=KEY_ADULT,
            conclusion=decision.adult.conclusion.value,
            summary_code=decision.adult.summary_code,
            summary_parameters=reference,
            input_links=(
                InputLinkSpec(
                    LinkInputKind.ROUTE_PROFILE_VERSION,
                    inputs.route_profile_version_id,
                    input_key="date_of_birth",
                ),
                date_link,
            ),
        ),
        EvaluatedResult(
            requirement_key=KEY_STATUS,
            conclusion=decision.status.conclusion.value,
            summary_code=decision.status.summary_code,
            input_links=(
                InputLinkSpec(
                    LinkInputKind.ROUTE_PROFILE_VERSION,
                    inputs.route_profile_version_id,
                    input_key="status_type",
                ),
            ),
        ),
        # The composite reads the profile answers directly (one input link), and composes
        # the adult/status *conclusions* — a result→result dependency §25.1 has no input
        # kind for. Those upstream conclusions are recorded as snapshots for explanation
        # only; the structural edge that must restale the composite when an upstream
        # restales is owned by selective invalidation (M6). Until then a change reaching
        # the composite re-runs the whole route set, so it stays correct — just not
        # selectively. Do NOT add an APPLICATION_DATE link here: the composite does not
        # read the date, and links must name only inputs actually read.
        EvaluatedResult(
            requirement_key=KEY_STANDARD,
            conclusion=decision.composite.conclusion.value,
            summary_code=decision.composite.summary_code,
            summary_parameters={
                "adult_conclusion": decision.adult.conclusion.value,
                "status_conclusion": decision.status.conclusion.value,
            },
            input_links=(profile_link,),
        ),
    ]
