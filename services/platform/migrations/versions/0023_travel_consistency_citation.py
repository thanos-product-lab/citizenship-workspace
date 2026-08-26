"""Drop a guidance citation that pointed at something the rule does not check

`0022` gave `residence.travel_consistency` v2.0.0 two citations: the data-quality one it
inherited from v1, and GUIDE_AN's "Documents you must provide with your application" for
the new coverage detection. The second is wrong, and wrong in a way worth naming.

That guidance is about what the **Home Office** requires. This rule does not check that. It
checks whether the *user* has attached a document to a trip, and nothing reads the document
(ADR-0021). A user following provenance from an unevidenced-trip finding would land on
guidance about a requirement the product has not assessed — false authority, which is the
same family of harm as false reassurance and is what directive 7 exists to prevent.

The detection is tagged **[PRODUCT]** in RULES_SPEC §7.8 precisely because no guidance
mandates it. The remaining citation covers what the rule actually adjudicates.

**A new migration rather than an edit to `0022`.** `0022` has run — locally and in CI — and
this repository does not mutate a migration that has run; `0020` corrected `0018`'s
constraint the same way. The cost is one more file; the alternative is a migration whose
recorded effect differs from what it did on databases that already applied it.

Revision ID: 0023_travel_consistency_citation
Revises: 0022_travel_consistency_v2
Create Date: 2026-08-26
"""

import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_travel_consistency_citation"
down_revision: str | None = "0022_travel_consistency_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KEY = "residence.travel_consistency"
_V2_ID = uuid.uuid5(uuid.UUID("6f1d2c3b-0a11-4e22-9c33-000000000022"), f"rule_version:{_KEY}")

_KEPT = [
    {
        "source": "GUIDE_AN",
        "section": "Absences from the UK (data quality over travel records)",
    }
]

_ORIGINAL = [
    *_KEPT,
    {
        "source": "GUIDE_AN",
        "section": "Documents you must provide with your application",
    }
]


def _set_guidance(citations: list[dict[str, str]]) -> None:
    # Rewrites only the `guidance` key, leaving anything else in `configuration`
    # untouched — a later slice may add configuration this migration knows nothing about.
    op.get_bind().execute(
        sa.text(
            "UPDATE rule_versions "
            # \`cast(... AS jsonb)\`, not \`::jsonb\`: SQLAlchemy's text() reads the second colon
            # of \`:guidance::jsonb\` as the start of another bind parameter.
            "SET configuration = jsonb_set(configuration, '{guidance}', cast(:guidance AS jsonb)) "
            "WHERE id = :id"
        ),
        {"guidance": json.dumps(citations), "id": _V2_ID},
    )


def upgrade() -> None:
    _set_guidance(_KEPT)


def downgrade() -> None:
    _set_guidance(_ORIGINAL)
