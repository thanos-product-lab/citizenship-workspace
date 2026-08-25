"""residence.travel_consistency v2.0.0: the rule learns about evidence

The first *second* rule version in the product, which makes this migration two things at
once — a catalog change and, for the first time, a rule-set transition.

**The catalog change.** v2.0.0 declares everything v1 did plus `EVIDENCE_SUPPORT /
ALL_ACTIVE_EVIDENCE_LINKS`, so attaching or detaching a document stales this requirement
through the ordinary selective-invalidation path (RULES_SPEC §8). v1 is RETIRED and given
an `effective_to`, so `list_active_dependencies` — which filters on ACTIVE — resolves
against v2 alone rather than seeing both and doubling every dependency.

**The transition, and why it stales results.** ADR-0014 recorded a gap: dependencies
resolve against the *currently active* rule version, not the version that produced the
result being invalidated. It was unreachable while every requirement had exactly one rule
version. This migration makes it reachable, so it also closes the hole it opens, the cheap
way (ADR-0022): every CURRENT result produced by v1 is marked STALE with reason
`RULE_VERSION_CHANGED`. No v1-produced result survives as current, so there is no result
for the active-version lookup to miss.

v2 happens only to *add* a dependency, which means the specific hazard would not have
fired this time. Relying on that would be relying on an accident of this one change — the
next version to *remove* a dependency would reintroduce it silently, with nothing failing.

The sweep is idempotent: it matches on `rule_version_id` and `currency = 'CURRENT'`, so
re-running it changes nothing. Conclusions are untouched — only currency moves, which is
directive 4 (conclusion and currency are separate) and ADR-0001.

Revision ID: 0022_travel_consistency_v2
Revises: 0021_evidence_travel_links
Create Date: 2026-08-25
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022_travel_consistency_v2"
down_revision: str | None = "0021_evidence_travel_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "residence.travel_consistency"
_RULE_SET = "2026.07.0"
_SEMVER = "2.0.0"
_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000022")

#: v1's id, minted by 0009 from its own namespace. Recomputed here rather than looked up
#: by `semantic_version`, so retiring the right row does not depend on a string nobody
#: has constrained to be unique.
_V1_NS = uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000009")
_V1_ID = uuid.uuid5(_V1_NS, f"rule_version:{_KEY}")
_V2_ID = uuid.uuid5(_NS, f"rule_version:{_KEY}")

_GUIDANCE = [
    {
        "source": "GUIDE_AN",
        "section": "Absences from the UK (data quality over travel records)",
    },
    # v2's new reading. Cited because CLAUDE.md and the new-rule skill both require every
    # rule to cite guidance for what it checks, and coverage is a new thing it checks.
    {
        "source": "GUIDE_AN",
        "section": "Documents you must provide with your application",
    },
]

#: v1's two, plus the evidence one. Declared in full rather than copied by reference: a
#: rule version owns its dependency set, and inheriting v1's would make v2's behaviour
#: depend on a row someone might later edit.
_DEPENDENCIES: list[tuple[str, str | None, str, bool]] = [
    ("PROPOSED_APPLICATION_DATE", None, "ANY_CURRENT_VERSION", True),
    ("TRAVEL_RECORD", None, "ALL_ACTIVE_TRAVEL_RECORDS", False),
    # Not `required`: a case with no attached documents is a case this rule evaluates
    # perfectly well, and it says so. `required` would make coverage a precondition for
    # reaching a verdict at all.
    ("EVIDENCE_SUPPORT", None, "ALL_ACTIVE_EVIDENCE_LINKS", False),
]


def _dependency_id(kind: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"dependency:{_KEY}:{kind}")


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)

    requirement_id = bind.execute(
        sa.text("SELECT id FROM requirement_definitions WHERE requirement_key = :key"),
        {"key": _KEY},
    ).scalar_one()

    rule_versions = sa.table(
        "rule_versions",
        sa.column("id", sa.Uuid),
        sa.column("requirement_id", sa.Uuid),
        sa.column("semantic_version", sa.String),
        sa.column("rule_set", sa.String),
        sa.column("evaluator_key", sa.String),
        sa.column("configuration", postgresql.JSONB),
        sa.column("effective_from", sa.DateTime),
        sa.column("lifecycle_status", sa.String),
    )
    dependencies = sa.table(
        "rule_dependency_definitions",
        sa.column("id", sa.Uuid),
        sa.column("rule_version_id", sa.Uuid),
        sa.column("input_kind", sa.String),
        sa.column("input_key", sa.String),
        sa.column("dependency_scope", sa.String),
        sa.column("required", sa.Boolean),
    )

    op.bulk_insert(
        rule_versions,
        [
            {
                "id": _V2_ID,
                "requirement_id": requirement_id,
                "semantic_version": _SEMVER,
                "rule_set": _RULE_SET,
                "evaluator_key": _KEY,
                "configuration": {"guidance": _GUIDANCE},
                "effective_from": now,
                "lifecycle_status": "ACTIVE",
            }
        ],
    )
    op.bulk_insert(
        dependencies,
        [
            {
                "id": _dependency_id(kind),
                "rule_version_id": _V2_ID,
                "input_kind": kind,
                "input_key": input_key,
                "dependency_scope": scope,
                "required": required,
            }
            for kind, input_key, scope, required in _DEPENDENCIES
        ],
    )

    # Retire v1. Both columns matter: `lifecycle_status` is what the dependency and
    # evaluator lookups filter on, and `effective_to` is what makes the catalog readable
    # to a person asking when the rules changed.
    bind.execute(
        sa.text(
            "UPDATE rule_versions SET lifecycle_status = 'RETIRED', effective_to = :now "
            "WHERE id = :id"
        ),
        {"now": now, "id": _V1_ID},
    )

    # ADR-0022's sweep. Currency only — the conclusion each result reached under v1 stays
    # exactly as it was, and the result stays inspectable with its original rule version
    # and input links (directive 3).
    bind.execute(
        sa.text(
            # The same three columns `AssessmentResult.mark_stale` writes, and only
            # those. SQL rather than the ORM because a migration must not depend on the
            # application model, which will drift away from this schema version.
            "UPDATE assessment_results "
            "SET currency = 'STALE', stale_reason_code = 'RULE_VERSION_CHANGED', "
            "    marked_stale_at = :now "
            "WHERE rule_version_id = :v1 AND currency = 'CURRENT'"
        ),
        {"now": now, "v1": _V1_ID},
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(
        sa.text("DELETE FROM rule_dependency_definitions WHERE rule_version_id = :id").bindparams(
            sa.bindparam("id", value=_V2_ID)
        )
    )
    op.execute(
        sa.text("DELETE FROM rule_versions WHERE id = :id").bindparams(
            sa.bindparam("id", value=_V2_ID)
        )
    )
    bind.execute(
        sa.text(
            "UPDATE rule_versions SET lifecycle_status = 'ACTIVE', effective_to = NULL "
            "WHERE id = :id"
        ),
        {"id": _V1_ID},
    )
    # The swept results are deliberately *not* un-staled. Marking something stale is a
    # statement that it needs rechecking, and rolling the catalog back does not make that
    # untrue — the results were produced before this deployment either way, and a
    # recalculation is cheap. Restoring CURRENT would be asserting freshness nothing
    # re-established.
