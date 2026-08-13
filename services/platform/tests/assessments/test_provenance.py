"""Provenance is exact: a result links precisely the inputs its rule declared — no more,
no fewer. This is the subtlest trust bug in the system (an undeclared read passes every
value test yet silently breaks selective invalidation), so the check is strict set
equality in both directions, per in-scope requirement.

A rule *declares* dependencies by input class (ROUTE_PROFILE); a result *links* the
concrete version read (ROUTE_PROFILE_VERSION). The test maps one to the other and asserts
the (kind, input_key) sets are equal.

Scope: this checks *input-version* provenance only. `route.standard_section_6_1` also
depends on the adult/status *conclusions* — a result→result edge §25.1 has no input kind
for — which is deliberately not a link and is owned by selective invalidation (M6,
ADR-0007). So a green here does not by itself prove the composite is invalidation-complete.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInputLink, AssessmentResult
from app.requirements.domain import Currency
from app.requirements.models import (
    RequirementDefinition,
    RuleDependencyDefinition,
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
# strict (kind, input_key) set. status.holding_period joins the three route rules here.
ROUTE_KEYS = (
    "route.adult_applicant",
    "route.supported_status",
    "route.standard_section_6_1",
    "status.holding_period",
)

# A rule's declared dependency kind → the version-link kind a result records for it.
_DEPENDENCY_TO_LINK = {
    "ROUTE_PROFILE": "ROUTE_PROFILE_VERSION",
    "PROPOSED_APPLICATION_DATE": "APPLICATION_DATE_VERSION",
    "TRAVEL_RECORD": "TRAVEL_RECORD_VERSION",
}


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

    for key in ROUTE_KEYS:
        definition = db_session.scalar(
            select(RequirementDefinition).where(RequirementDefinition.requirement_key == key)
        )
        assert definition is not None
        rule_version = db_session.scalar(
            select(RuleVersion).where(RuleVersion.requirement_id == definition.id)
        )
        assert rule_version is not None

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
    for departure, return_ in (("2023-06-01", "2023-07-02"), ("2024-02-01", "2024-03-01")):
        api("user_a").post(
            f"/api/v1/cases/{case_id}/travel-records",
            json={
                "destination_label": "Trip",
                "departure_date": departure,
                "return_date": return_,
                "date_confidence": "EXACT",
                "review_state": "CONFIRMED",
            },
        )
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")

    active_travel_version_ids = {
        row.id
        for row in db_session.scalars(select(TravelRecordVersion))
        # every seeded trip has exactly one version here, all active
    }

    for key in (
        "residence.physical_presence_start_date",
        "residence.total_absences",
        "residence.final_year_absences",
        "residence.travel_consistency",
    ):
        definition = db_session.scalar(
            select(RequirementDefinition).where(RequirementDefinition.requirement_key == key)
        )
        assert definition is not None
        rule_version = db_session.scalar(
            select(RuleVersion).where(RuleVersion.requirement_id == definition.id)
        )
        assert rule_version is not None
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
