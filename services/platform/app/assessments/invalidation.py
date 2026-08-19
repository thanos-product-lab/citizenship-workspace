"""Selective stale propagation: the transactional seam between an input change and the
assessment results that depend on it (Domain §41, §48.5).

When an assessed input changes, the results whose rules **declare a dependency on that kind
of input** are marked STALE in the same transaction as the change — the conclusion is
untouched, only its currency, so the user sees the last conclusion clearly flagged as needing
recalculation rather than silently hidden or silently trusted.

This replaces M3B's blunt rule (ADR-0008: any residence input change stales every residence
result), which was wrong in two directions. It over-fired inside residence, staling
`residence.qualifying_period` for travel changes it does not depend on. More seriously it
under-fired across groups: an application-date change left `status.holding_period` and the
route rules reading CURRENT while the date beneath them had moved. Over-firing is noise;
under-firing is silent false reassurance, and nothing fails when it happens. See ADR-0014.

Two declaration sources drive the resolution, both read from the catalog rather than
hardcoded here:

- `rule_dependency_definitions` — the input kinds each rule reads (§25).
- `rule_composition_edges` — the *conclusions* each rule composes (§25.4). Transitive: if an
  upstream result is stale its conclusion is no longer known-current, so everything composing
  it is stale too.

This module imports only repositories — never another module's service — so the residence
write commands can call it without an import cycle.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInvalidated
from app.assessments.repository import AssessmentRepository, RequirementCatalogRepository
from app.requirements.models import DependencyInputKind
from app.shared.unit_of_work import UnitOfWork


class StaleReason:
    APPLICATION_DATE_CHANGED = "APPLICATION_DATE_CHANGED"
    TRAVEL_RECORD_CHANGED = "TRAVEL_RECORD_CHANGED"
    ROUTE_PROFILE_CHANGED = "ROUTE_PROFILE_CHANGED"


@dataclass(frozen=True)
class InvalidationOutcome:
    """What the change actually staled. `requirement_keys` is the *resolved* set — the
    requirements whose declarations matched — while `result_ids` covers only those that had a
    CURRENT result to mark. The two differ whenever a requirement is unassessed or already
    stale, which is why both are reported."""

    requirement_keys: frozenset[str]
    result_ids: tuple[uuid.UUID, ...]

    @property
    def affected_count(self) -> int:
        return len(self.result_ids)


def resolve_affected_requirements(
    session: Session, *, input_kind: DependencyInputKind, input_key: str | None
) -> frozenset[str]:
    """The requirement keys a change of this kind invalidates, by declaration.

    Key matching, which is the subtlest part of this file:

    | declared `input_key` | change names a key | change names no key |
    |---|---|---|
    | NULL                 | matches            | matches             |
    | "status_granted_on"  | matches iff equal  | matches             |

    A change that does not say *which* field moved matches every declaration of its kind.
    That over-fires, and over-firing is safe — it costs a needless recalculation. The
    opposite default would under-fire, which is the failure this module exists to prevent.
    """
    directly_affected = {
        requirement_key
        for requirement_key, dependency in RequirementCatalogRepository.list_active_dependencies(
            session
        )
        if dependency.input_kind == input_kind.value
        and (dependency.input_key is None or input_key is None or dependency.input_key == input_key)
    }
    return _close_over_composition(
        directly_affected, RequirementCatalogRepository.list_active_composition_edges(session)
    )


def _close_over_composition(
    seed: Collection[str], edges: Collection[tuple[str, str]]
) -> frozenset[str]:
    """Expand a set of stale requirements over composition edges to a fixed point.

    Iterates rather than recursing one level, and tracks what it has already added, because
    the edges are not guaranteed acyclic: RULES_SPEC §8 makes `referees.first` and
    `referees.second` mutually dependent through their cross-slot check. Neither has an
    evaluator yet, so no cycle exists in the seeded data today — but a loop written on the
    assumption of a DAG would hang rather than fail when one arrives.
    """
    affected = set(seed)
    while True:
        added = {
            downstream
            for downstream, upstream in edges
            if upstream in affected and downstream not in affected
        }
        if not added:
            return frozenset(affected)
        affected |= added


def invalidate_for_input_change(
    session: Session,
    uow: UnitOfWork,
    *,
    case_id: uuid.UUID,
    input_kind: DependencyInputKind,
    reason_code: str,
    input_key: str | None = None,
) -> InvalidationOutcome:
    """Mark every result depending on this input STALE and, if any were, emit
    `AssessmentInvalidated` on the caller's unit of work — so the marks, the event and the
    input change commit atomically or not at all (§41.2). A no-op before the first assessment
    run exists: there is nothing to invalidate."""
    requirement_keys = resolve_affected_requirements(
        session, input_kind=input_kind, input_key=input_key
    )
    marked = AssessmentRepository.mark_current_results_stale(
        session, case_id, requirement_keys, reason_code, datetime.now(UTC)
    )
    outcome = InvalidationOutcome(
        requirement_keys=requirement_keys,
        result_ids=tuple(result_id for _, result_id in marked),
    )
    if marked:
        uow.emit(
            AssessmentInvalidated(
                aggregate_id=case_id,
                reason_code=reason_code,
                affected_count=len(marked),
                requirement_keys=tuple(sorted(key for key, _ in marked)),
            ),
            case_id=case_id,
            action="assessment.invalidated",
            target_type="ApplicationCase",
            target_id=case_id,
        )
    return outcome
