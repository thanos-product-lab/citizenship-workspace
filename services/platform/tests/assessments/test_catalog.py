"""The migration-seeded catalog and the app's in-scope evaluator set must not drift.

The requirement catalogue values live in migration 0007 (their single source); the app
(`requirements.evaluation`) owns which keys have evaluators. This test is the seam that
keeps the two honest: every in-scope key must be catalogued and have an active rule
version that cites guidance, the full catalogue is the documented 15, and no rule version
is seeded for a key that has no evaluator yet.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.requirements.evaluation import IN_SCOPE_REQUIREMENT_KEYS
from app.requirements.models import RequirementDefinition, RuleVersion

pytestmark = pytest.mark.integration

# The full catalogue of requirement keys (Domain §23.2). Kept here as an independent
# transcription so a drift in either the migration or the app trips the test.
ALL_REQUIREMENT_KEYS = {
    "route.adult_applicant",
    "route.supported_status",
    "route.standard_section_6_1",
    "status.holding_period",
    "residence.qualifying_period",
    "residence.physical_presence_start_date",
    "residence.total_absences",
    "residence.final_year_absences",
    "residence.travel_consistency",
    "knowledge.life_in_uk",
    "knowledge.english_language",
    "referees.first",
    "referees.second",
    "character.review",
    "preparation.case_complete",
}


def test_all_requirement_keys_are_catalogued(db_session: Session) -> None:
    keys = set(db_session.scalars(select(RequirementDefinition.requirement_key)))
    assert keys == ALL_REQUIREMENT_KEYS


def test_in_scope_keys_have_active_rule_versions_that_cite_guidance(db_session: Session) -> None:
    rows = db_session.execute(
        select(RequirementDefinition.requirement_key, RuleVersion).join(
            RuleVersion, RuleVersion.requirement_id == RequirementDefinition.id
        )
    ).all()
    versioned_keys = {key for key, _ in rows}

    # Exactly the in-scope evaluators have a seeded rule version — no more (nothing seeded
    # for a key without an evaluator), no fewer (every evaluator is backed).
    assert versioned_keys == set(IN_SCOPE_REQUIREMENT_KEYS)

    for _key, version in rows:
        assert version.lifecycle_status == "ACTIVE"
        assert version.configuration.get("guidance"), "every rule cites at least one source"
