"""Selective invalidation may narrow what blunt invalidation staled, but only by declaration.

Blunt invalidation (M3B, ADR-0008) staled all five residence results on any residence input
change. It over-fired, which is safe. Selective invalidation narrows that set, and narrowing
is where the danger is: a requirement dropped from the set reads CURRENT while its inputs
have moved, no test goes red, and the screen shows a confident conclusion nobody rechecked.

So the tests here are differential. For each input change, the set selective invalidation
produces must contain everything blunt would have caught, *except* requirements that declare
no dependency of the changed kind. The exception set is computed from the declaration rows,
never written by hand — hard-coding "qualifying_period is fine to drop" would just restate
the bug as an assertion.

This file checks the *resolution*, directly against the catalog. `test_stale.py` checks the
same behaviour through the API, and `test_invalidation_completeness.py` checks it against
observed recalculation output rather than against declarations at all.
"""

import pytest
from sqlalchemy.orm import Session

from app.assessments.invalidation import resolve_affected_requirements
from app.assessments.repository import RequirementCatalogRepository
from app.requirements.evaluation import (
    IN_SCOPE_REQUIREMENT_KEYS,
    RESIDENCE_REQUIREMENT_KEYS,
)
from app.requirements.models import DependencyInputKind

pytestmark = pytest.mark.integration


def _declaring(session: Session, kind: DependencyInputKind) -> set[str]:
    """Requirements whose ACTIVE rule declares a dependency of this kind — from the rows,
    not from a list in this file."""
    return {
        requirement_key
        for requirement_key, dependency in RequirementCatalogRepository.list_active_dependencies(
            session
        )
        if dependency.input_kind == kind.value
    }


def test_travel_change_keeps_everything_blunt_caught_that_declares_travel(
    db_session: Session,
) -> None:
    selective = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.TRAVEL_RECORD
    )
    blunt = set(RESIDENCE_REQUIREMENT_KEYS)
    independent = blunt - _declaring(db_session, DependencyInputKind.TRAVEL_RECORD)

    assert blunt - independent <= selective, (
        "selective invalidation dropped a requirement that blunt caught and that declares a "
        f"travel dependency: {sorted((blunt - independent) - selective)}"
    )
    # And the only thing it dropped is the one that declares no travel dependency at all.
    assert blunt - selective == independent == {"residence.qualifying_period"}


def test_application_date_change_is_a_superset_of_the_blunt_residence_set(
    db_session: Session,
) -> None:
    selective = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.PROPOSED_APPLICATION_DATE
    )
    # Every residence rule declares the date, so here selective strictly *widens* the blunt
    # set rather than narrowing it — this is the direction ADR-0008 got wrong.
    assert set(RESIDENCE_REQUIREMENT_KEYS) <= selective
    assert {"status.holding_period", "route.adult_applicant"} <= selective


def test_application_date_fan_out_is_the_declared_set_plus_composition_closure(
    db_session: Session,
) -> None:
    """The fan-out oracle, computed rather than asserted as a bare literal.

    RULES_SPEC §8 also says "eight", but it is a *different* eight: counting its table, the
    direct application-date dependants are the seven we have plus `knowledge.english_language`,
    with the composite excluded — so the spec's closure is nine and ours is eight only because
    `english_language` has no evaluator yet. Two eights agreeing by coincidence is a trap: when
    M9 gives that rule an evaluator our count becomes nine, and anyone reconciling a hardcoded
    8 against the spec could "fix" it by deleting the composition edge, reopening the exact
    under-invalidation hole ADR-0014 closed. So the expectation is derived, and the literal
    below is a sanity check carrying its own derivation.
    """
    direct = _declaring(db_session, DependencyInputKind.PROPOSED_APPLICATION_DATE)
    edges = RequirementCatalogRepository.list_active_composition_edges(db_session)
    expected = direct | {downstream for downstream, upstream in edges if upstream in direct}

    selective = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.PROPOSED_APPLICATION_DATE
    )
    assert selective == expected

    assert len(direct) == 7, sorted(direct)
    assert selective - direct == {"route.standard_section_6_1"}
    assert len(selective) == 8, (
        f"expected 7 declared date dependants + the composite = 8, got {sorted(selective)}"
    )


def test_the_composite_is_reachable_only_through_its_composition_edge(
    db_session: Session,
) -> None:
    """The single most likely under-fire in the design, pinned.

    `route.standard_section_6_1` declares no application-date dependency, because it does not
    read the date — it composes `route.adult_applicant`'s conclusion, and *that* rule reads
    the date. Resolve from input-version dependencies alone and the composite is missed while
    the conclusion beneath it moves.
    """
    direct = _declaring(db_session, DependencyInputKind.PROPOSED_APPLICATION_DATE)
    assert "route.standard_section_6_1" not in direct

    selective = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.PROPOSED_APPLICATION_DATE
    )
    assert "route.standard_section_6_1" in selective


def test_a_change_matches_every_declaration_of_its_kind_regardless_of_key(
    db_session: Session,
) -> None:
    """Resolution matches on input *kind* only; a declared `input_key` never narrows it.

    Three rules declare keyed ROUTE_PROFILE dependencies (`date_of_birth`, `status_type`,
    `status_granted_on`), and narrowing on them looks free: why stale a rule reading only the
    grant date when the date of birth moved? Because `RouteProfileVersion` is a whole-row
    snapshot — `confirmed_copy` mints a new version id for a change to *any* field — so after
    that change every rule reading the profile holds a CURRENT result whose recorded
    ROUTE_PROFILE_VERSION link names a superseded version. Narrowing would leave it there,
    breaking "every current trusted assessment references current relevant input versions"
    (CLAUDE.md §9), and nothing in the suite would catch it.

    Narrowing on a key is sound only for an input versioned *per key*. None is. If one ever
    exists, revisit this citing that input's versioning — not the key's mere presence.
    """
    declaring = _declaring(db_session, DependencyInputKind.ROUTE_PROFILE)
    resolved = resolve_affected_requirements(
        db_session, input_kind=DependencyInputKind.ROUTE_PROFILE
    )
    assert declaring <= resolved
    # Every keyed declarer is included, including those naming a field that did not move.
    assert {
        "route.adult_applicant",
        "route.supported_status",
        "status.holding_period",
    } <= resolved


def test_a_kind_no_rule_declares_invalidates_nothing(db_session: Session) -> None:
    """Domain §41.5's last row: an unrelated input invalidates nothing, unless a rule declares
    it. No rule reads evidence support yet."""
    assert (
        resolve_affected_requirements(db_session, input_kind=DependencyInputKind.EVIDENCE_SUPPORT)
        == frozenset()
    )


def test_resolution_never_names_a_requirement_without_an_evaluator(db_session: Session) -> None:
    """Six catalogued requirements have no rule version yet. They must never appear in an
    invalidation set: there is no result to stale, and naming them would make the affected
    count disagree with what the user can see."""
    for kind in DependencyInputKind:
        resolved = resolve_affected_requirements(db_session, input_kind=kind)
        assert resolved <= set(IN_SCOPE_REQUIREMENT_KEYS), sorted(
            resolved - set(IN_SCOPE_REQUIREMENT_KEYS)
        )
