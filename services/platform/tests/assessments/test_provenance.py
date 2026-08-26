"""Provenance is exact: a result links precisely the inputs its rule declared — no more,
no fewer. This is the subtlest trust bug in the system (an undeclared read passes every
value test yet silently breaks selective invalidation), so the check is strict set
equality in both directions, per in-scope requirement.

A rule *declares* dependencies by input class (ROUTE_PROFILE); a result *links* the
concrete version read (ROUTE_PROFILE_VERSION). The test maps one to the other and asserts
the (kind, input_key) sets are equal.

`route.standard_section_6_1` also depends on the adult/status *conclusions* — a
result→result edge §25.1 has no input kind for, so deliberately not a link. Since ADR-0014
that edge is declared in `rule_composition_edges`, and
`test_composition_edges_match_the_conclusions_the_composite_records` below holds it to the
same strict equality. Between the two, every input a rule reads is declared somewhere the
invalidation service also reads.

What this file still cannot prove: that a rule does not read an input it neither links nor
declares. Nothing structural reveals that — only behaviour does, which is what
`test_invalidation_completeness.py` is for.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult
from app.requirements.domain import Currency
from app.requirements.evaluation import IN_SCOPE_REQUIREMENT_KEYS
from app.requirements.models import (
    RequirementDefinition,
    RuleCompositionEdge,
    RuleDependencyDefinition,
    RuleLifecycleStatus,
    RuleVersion,
)
from app.residence.domain import TravelRecordVersion

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

SUPPORTED_ANSWERS = {
    "date_of_birth": "1990-05-01",
    "status_type": "ILR",
    "status_granted_on": "2019-01-01",
    "married_to_british_citizen": False,
    "may_already_be_british": False,
}
# Rules with only scalar (ANY_CURRENT_VERSION) dependencies, so links == declared deps as a
# strict (kind, input_key) set. `residence.qualifying_period` belongs here despite its group:
# it reads the application date and nothing else, which is exactly why a travel change must
# not stale it (ADR-0014). It was previously in neither provenance test — the one rule whose
# narrowing selective invalidation depends on was the one rule with no provenance check.
SCALAR_DEPENDENCY_KEYS = (
    "route.adult_applicant",
    "route.supported_status",
    "route.standard_section_6_1",
    "status.holding_period",
    "residence.qualifying_period",
)

# Rules declaring ALL_ACTIVE_TRAVEL_RECORDS, which fans out to one link per active record —
# so kinds are checked strictly and the travel links are checked against the active set.
TRAVEL_FANOUT_KEYS = (
    "residence.physical_presence_start_date",
    "residence.total_absences",
    "residence.final_year_absences",
    "residence.travel_consistency",
)

# The composite records each upstream conclusion under its own summary-parameter name.
# Spelled out rather than derived by string surgery, so a third upstream added to the rule
# fails the assertion below with a readable message instead of being silently mis-mapped.
_SUMMARY_PARAMETER_TO_REQUIREMENT = {
    "adult_conclusion": "route.adult_applicant",
    "status_conclusion": "route.supported_status",
}

# A rule's declared dependency kind → the version-link kind a result records for it.
_DEPENDENCY_TO_LINK = {
    "ROUTE_PROFILE": "ROUTE_PROFILE_VERSION",
    "PROPOSED_APPLICATION_DATE": "APPLICATION_DATE_VERSION",
    "TRAVEL_RECORD": "TRAVEL_RECORD_VERSION",
    # Not `_VERSION`: an evidence link has no version sequence, only availability
    # (Domain §31.1).
    "EVIDENCE_SUPPORT": "EVIDENCE_LINK",
}


def _active_rule_version(session: Session, requirement_id: uuid.UUID) -> RuleVersion:
    """The one ACTIVE rule version for a requirement.

    The filter is the whole point, and its absence was a silent hole. Until M7 slice 4a
    every requirement had exactly one rule version, so an unfiltered `scalar()` was
    harmless — then `residence.travel_consistency` v1 was retired and v2 activated, and
    this guard started comparing results against **retired v1's** declarations. It went on
    passing, because the fixture builds a case with no evidence, so the result carried no
    `EVIDENCE_LINK` rows to disagree about. The one dependency this milestone added was
    the one the guard had stopped checking.

    Asserting exactly one row rather than taking the first: two ACTIVE versions would
    double every declared dependency, and a guard that silently picked one of them would
    be back where it started.
    """
    versions = list(
        session.scalars(
            select(RuleVersion).where(
                RuleVersion.requirement_id == requirement_id,
                RuleVersion.lifecycle_status == RuleLifecycleStatus.ACTIVE.value,
            )
        )
    )
    assert len(versions) == 1, f"expected exactly one active rule version, got {len(versions)}"
    return versions[0]


def _attach_a_document(api: Api, case_id: str, travel_record_id: str) -> None:
    """Upload one document and attach it to a trip, through the real commands."""
    from app.core.storage import InMemoryStorage, get_storage
    from tests.evidence.conftest import fixture_bytes

    content = fixture_bytes("travel-booking.pdf")
    grant = (
        api("user_a")
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": len(content)},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), content)
    item = api("user_a").post(
        f"/api/v1/cases/{case_id}/evidence",
        json={
            "upload_token": grant["upload_token"],
            "category": "TRAVEL_SUPPORT",
            "display_name": "A booking",
            "original_filename": "booking.pdf",
        },
    )
    api("user_a").post(
        f"/api/v1/cases/{case_id}/travel-records/{travel_record_id}/evidence",
        json={"evidence_item_id": item.json()["id"]},
    )


def _case_with_date(api: Api, user: str) -> str:
    case_id = str(api(user).post("/api/v1/cases", json={"title": "My case"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})
    api(user).post(
        f"/api/v1/cases/{case_id}/application-dates/select",
        json={"application_date": "2027-04-15"},
    )
    return case_id


def test_input_links_equal_declared_dependencies(api: Api, db_session: Session) -> None:
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    for key in SCALAR_DEPENDENCY_KEYS:
        definition = db_session.scalar(
            select(RequirementDefinition).where(RequirementDefinition.requirement_key == key)
        )
        assert definition is not None
        rule_version = _active_rule_version(db_session, definition.id)

        declared = {
            (_DEPENDENCY_TO_LINK[dep.input_kind], dep.input_key)
            for dep in db_session.scalars(
                select(RuleDependencyDefinition).where(
                    RuleDependencyDefinition.rule_version_id == rule_version.id
                )
            )
        }

        result = db_session.scalar(
            select(AssessmentResult).where(
                AssessmentResult.requirement_id == definition.id,
                AssessmentResult.currency == Currency.CURRENT.value,
            )
        )
        assert result is not None
        linked = {
            (link.input_kind, link.input_key)
            for link in db_session.scalars(
                select(AssessmentInputLink).where(
                    AssessmentInputLink.assessment_result_id == result.id
                )
            )
        }

        # Strict equality both directions: no undeclared link, no unlinked dependency.
        assert linked == declared, f"{key}: links {linked} != declared {declared}"


def test_residence_links_cover_declared_kinds_and_every_active_trip(
    api: Api, db_session: Session
) -> None:
    # Residence rules declare an ALL_ACTIVE_TRAVEL_RECORDS dependency, which resolves to one
    # link per active record — so the invariant is: link *kinds* equal declared *kinds*, and
    # the travel links are exactly the case's active travel-record versions.
    case_id = _case_with_date(api, "user_a")
    trip_ids = []
    for departure, return_ in (("2023-06-01", "2023-07-02"), ("2024-02-01", "2024-03-01")):
        trip_ids.append(
            str(
                api("user_a")
                .post(
                    f"/api/v1/cases/{case_id}/travel-records",
                    json={
                        "destination_label": "Trip",
                        "departure_date": departure,
                        "return_date": return_,
                        "date_confidence": "EXACT",
                        "review_state": "CONFIRMED",
                    },
                )
                .json()["id"]
            )
        )
    # And one attached document, so `residence.travel_consistency`'s EVIDENCE_SUPPORT
    # dependency actually fans out to a link. A fixture with no evidence produces zero
    # `EVIDENCE_LINK` rows, which is correct behaviour and leaves the strict kind-equality
    # below with nothing to compare — the same reason this fixture has always created
    # trips rather than asserting against an empty case.
    _attach_a_document(api, case_id, trip_ids[0])
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    active_travel_version_ids = {
        row.id
        for row in db_session.scalars(select(TravelRecordVersion))
        # every seeded trip has exactly one version here, all active
    }

    for key in TRAVEL_FANOUT_KEYS:
        definition = db_session.scalar(
            select(RequirementDefinition).where(RequirementDefinition.requirement_key == key)
        )
        assert definition is not None
        rule_version = _active_rule_version(db_session, definition.id)
        declared_kinds = {
            _DEPENDENCY_TO_LINK[dep.input_kind]
            for dep in db_session.scalars(
                select(RuleDependencyDefinition).where(
                    RuleDependencyDefinition.rule_version_id == rule_version.id
                )
            )
        }
        result = db_session.scalar(
            select(AssessmentResult).where(
                AssessmentResult.requirement_id == definition.id,
                AssessmentResult.currency == Currency.CURRENT.value,
            )
        )
        assert result is not None
        links = list(
            db_session.scalars(
                select(AssessmentInputLink).where(
                    AssessmentInputLink.assessment_result_id == result.id
                )
            )
        )
        assert {link.input_kind for link in links} == declared_kinds  # no undeclared kind
        travel_ids = {
            link.input_version_id for link in links if link.input_kind == "TRAVEL_RECORD_VERSION"
        }
        assert travel_ids == active_travel_version_ids  # every active trip, exactly


def test_every_in_scope_rule_is_covered_by_a_provenance_test() -> None:
    """No evaluated rule may sit outside both checks above.

    `residence.qualifying_period` did exactly that until ADR-0014: in neither key list, so
    its links were never compared to its declarations, so nothing would have caught it
    reading an input it had not declared. The gap was invisible because both tests passed.
    A coverage assertion is cheap; noticing the omission by eye evidently is not.
    """
    covered = set(SCALAR_DEPENDENCY_KEYS) | set(TRAVEL_FANOUT_KEYS)
    assert covered == set(IN_SCOPE_REQUIREMENT_KEYS), (
        "requirements with an evaluator but no provenance check: "
        f"{sorted(set(IN_SCOPE_REQUIREMENT_KEYS) - covered)}"
    )


def test_composition_edges_match_the_conclusions_the_composite_records(
    api: Api, db_session: Session
) -> None:
    """The composite's declared composition edges equal the upstream conclusions it actually
    composed — strict equality, the same standard as input links.

    This is the result→result half of provenance. Selective invalidation stales the composite
    by walking these edges, so an edge missing here is an under-fire: the composite would read
    CURRENT after an upstream conclusion moved beneath it. An edge that is declared but not
    composed is the reverse — an over-fire, harmless, but still a lie about what the rule reads.
    """
    case_id = _case_with_date(api, "user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    definition = db_session.scalar(
        select(RequirementDefinition).where(
            RequirementDefinition.requirement_key == "route.standard_section_6_1"
        )
    )
    assert definition is not None
    rule_version = _active_rule_version(db_session, definition.id)

    declared = {
        edge.upstream_requirement_key
        for edge in db_session.scalars(
            select(RuleCompositionEdge).where(
                RuleCompositionEdge.rule_version_id == rule_version.id
            )
        )
    }
    result = db_session.scalar(
        select(AssessmentResult).where(
            AssessmentResult.requirement_id == definition.id,
            AssessmentResult.currency == Currency.CURRENT.value,
        )
    )
    assert result is not None

    composed = set()
    for name in result.summary_parameters:
        if not name.endswith("_conclusion"):
            continue
        assert name in _SUMMARY_PARAMETER_TO_REQUIREMENT, (
            f"the composite records {name!r} but no requirement is mapped to it — add the "
            "mapping and the matching composition edge, or this conclusion is composed "
            "without being declared, which selective invalidation cannot see"
        )
        composed.add(_SUMMARY_PARAMETER_TO_REQUIREMENT[name])

    assert composed == declared, f"composed {sorted(composed)} != declared {sorted(declared)}"
