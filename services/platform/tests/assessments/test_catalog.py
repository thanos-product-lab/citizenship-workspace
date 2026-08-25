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

from app.assessments.domain import AssessmentResult
from app.requirements.domain import Currency
from app.requirements.evaluation import IN_SCOPE_REQUIREMENT_KEYS
from app.requirements.models import (
    RequirementDefinition,
    RuleLifecycleStatus,
    RuleVersion,
)

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

    # Every rule version cites guidance, retired ones included: a historical result links
    # its producing version, and a user inspecting it is owed the sources that version
    # used, not the ones its successor uses.
    for _key, version in rows:
        assert version.configuration.get("guidance"), "every rule cites at least one source"

    # And exactly one *active* version per key. Until M7 slice 4a this test asserted every
    # version was ACTIVE, which happened to hold because no requirement had two — so
    # retiring `residence.travel_consistency` v1 turned it red for the right reason with
    # the wrong assertion. What the catalog actually has to guarantee is that the lookup
    # `list_active_dependencies` performs resolves to one version, since two would silently
    # double every dependency the rule declares.
    active_per_key: dict[str, int] = {}
    for key, version in rows:
        if version.lifecycle_status == "ACTIVE":
            active_per_key[key] = active_per_key.get(key, 0) + 1
    assert active_per_key == dict.fromkeys(IN_SCOPE_REQUIREMENT_KEYS, 1)


def test_no_result_produced_by_a_retired_rule_version_is_still_current(
    db_session: Session,
) -> None:
    """ADR-0022's sweep, asserted against the database rather than against the migration.

    The gap it closes: selective invalidation resolves dependencies against the *currently
    active* rule version, not the one that produced the result being invalidated. A
    v1-produced result left CURRENT is a result whose declared dependencies nobody is
    reading — so an input it genuinely read can move while it goes on being served as
    current, which CLAUDE.md §9 forbids.

    Migration `0022` sweeps them at activation, so this is an invariant about the whole
    catalog rather than about one migration: *any* future rule-version activation that
    forgets to sweep turns this red.

    Hard to see in a repository where every fixture is created after migrations have run,
    which is why the mutation matters more than the assertion — remove the sweep from
    `0022`, re-migrate a database holding a v1 result, and this fails.
    """
    stranded = db_session.execute(
        select(RuleVersion.semantic_version, AssessmentResult.id)
        .join(AssessmentResult, AssessmentResult.rule_version_id == RuleVersion.id)
        .where(
            RuleVersion.lifecycle_status != RuleLifecycleStatus.ACTIVE.value,
            AssessmentResult.currency == Currency.CURRENT.value,
        )
    ).all()

    assert stranded == [], (
        "these results were produced by a retired rule version and are still CURRENT; "
        "the activating migration must stale them (ADR-0022)"
    )


def test_the_activation_sweep_stales_a_result_the_retired_version_produced(
    api: "object", db_session: Session
) -> None:
    """The sweep's SQL, run against a result that genuinely points at the retired version.

    The invariant test above is the standing guard, but in this suite it passes trivially:
    every fixture is created after migrations have run, so no v1-produced result exists to
    strand. That makes it a guard with nothing to guard *here* — true of the deployed
    database, not of the test database.

    So this builds the state by hand: take a real result, point it at the retired v1, and
    run migration 0022's own statement. What it must do is move currency and nothing else
    — the conclusion the rule reached under v1 is still what it reached, and rewriting it
    would be editing an assessment in place (directive 3).
    """
    from sqlalchemy import text

    from app.seed.demo_case import seed_demo_case

    case_id = seed_demo_case(db_session, user_id="user_a")
    api("user_a").post(f"/api/v1/cases/{case_id}/assessments/recalculate")  # type: ignore[operator]
    db_session.expire_all()

    v1_id = db_session.execute(
        select(RuleVersion.id)
        .join(RequirementDefinition, RequirementDefinition.id == RuleVersion.requirement_id)
        .where(
            RequirementDefinition.requirement_key == "residence.travel_consistency",
            RuleVersion.semantic_version == "1.0.0",
        )
    ).scalar_one()

    result = db_session.execute(
        select(AssessmentResult)
        .join(RequirementDefinition, RequirementDefinition.id == AssessmentResult.requirement_id)
        .where(
            RequirementDefinition.requirement_key == "residence.travel_consistency",
            AssessmentResult.case_id == case_id,
            AssessmentResult.currency == Currency.CURRENT.value,
        )
    ).scalar_one()
    conclusion_before = result.conclusion
    result.rule_version_id = v1_id
    db_session.commit()

    db_session.execute(
        text(
            "UPDATE assessment_results "
            "SET currency = 'STALE', stale_reason_code = 'RULE_VERSION_CHANGED', "
            "    marked_stale_at = now() "
            "WHERE rule_version_id = :v1 AND currency = 'CURRENT'"
        ),
        {"v1": v1_id},
    )
    db_session.commit()
    db_session.expire_all()

    swept = db_session.get(AssessmentResult, result.id)
    assert swept is not None
    assert swept.currency == Currency.STALE.value
    assert swept.stale_reason_code == "RULE_VERSION_CHANGED"
    # Currency moved; the conclusion did not (directive 4, ADR-0001).
    assert swept.conclusion == conclusion_before
    assert swept.rule_version_id == v1_id, "history keeps the version that produced it"
