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
from app.issues import service as issues_service
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
    session: Session, *, input_kind: DependencyInputKind
) -> frozenset[str]:
    """The requirement keys a change of this kind invalidates, by declaration.

    **Matching is on input *kind* only, never on `input_key`.** Some dependency rows do name
    a field — `status.holding_period` declares `ROUTE_PROFILE/status_granted_on` — and it is
    tempting to narrow on that: a change to `date_of_birth` need not stale a rule that reads
    only the grant date.

    It is unsound, because narrowing on a key is only correct when the input is versioned
    *per key*, and none of ours is. A `RouteProfileVersion` is a whole-row snapshot: change
    any field and every rule reading that profile now links a superseded version id. Narrow
    on the key and a rule keeps a CURRENT result whose recorded `ROUTE_PROFILE_VERSION` link
    points at a version that no longer exists — breaking "every current trusted assessment
    references current relevant input versions" (CLAUDE.md §9) in a way nothing would catch.

    So keys stay what they already are: provenance, recorded on `AssessmentInputLink` and
    checked by the strict-equality test. They are documentation of what a rule reads, not a
    filter on what a change touches. If a per-field-versioned input kind ever exists, this is
    the decision to revisit — with that input's versioning as the reason, not the key's mere
    presence.
    """
    directly_affected = {
        requirement_key
        for requirement_key, dependency in RequirementCatalogRepository.list_active_dependencies(
            session
        )
        if dependency.input_kind == input_kind.value
    }
    return _close_over_composition(
        directly_affected, RequirementCatalogRepository.list_active_composition_edges(session)
    )


def _close_over_composition(
    seed: Collection[str], edges: Collection[tuple[str, str]]
) -> frozenset[str]:
    """Expand a set of stale requirements over composition edges to a fixed point.

    Iterates to a fixed point rather than expanding one level, because composition chains
    can be deeper than one hop. Today's only edge is one hop, but `preparation.case_complete`
    composes every other result (RULES_SPEC §8), so once it has an evaluator
    `case_complete → standard_section_6_1 → adult_applicant` is a two-hop walk that a
    single-level expansion would under-fire on.

    The loop also tolerates a cycle — it tracks what it has already added and stops on the
    first empty delta — but no cycle exists in the composition graph. (The mutual dependency
    between the two referee slots is a `REFEREE_RECORD` *input* dependency on both sides, not
    a composition edge, so it is matched in a single pass and never reaches this function.)
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
) -> InvalidationOutcome:
    """Mark every result depending on this input STALE and, if any were, emit
    `AssessmentInvalidated` on the caller's unit of work — so the marks, the event and the
    input change commit atomically or not at all (§41.2). A no-op before the first assessment
    run exists: there is nothing to invalidate."""
    requirement_keys = resolve_affected_requirements(session, input_kind=input_kind)
    marked = AssessmentRepository.mark_named_results_stale(
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

    # Reconcile the issue queue here rather than at each call site. A stale result and the
    # issue announcing it must never disagree, and a convention repeated at four call sites
    # is one a future writer forgets — the CSV-import seam had already been added without
    # it, which would have left a bulk import staling conclusions while the queue read
    # "nothing needs your attention". Same session, same unit of work, so both commit or
    # neither does.
    issues_service.reconcile(session, uow, case_id=case_id)
    return outcome
