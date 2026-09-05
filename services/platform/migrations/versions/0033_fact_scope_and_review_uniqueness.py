"""Give a fact a scope, and let a claim be decided exactly once

Three corrections from the M8 slice 3a reviews. Two of them were found by both the trust
and the security review independently, which is usually a sign the thing was wrong in a
way that was easy to walk past.

**1. `case_facts` had no scope, so a two-leg booking overwrote itself.**
`ExtractedClaim` carries `journey_index` precisely because `travel.departure_date` at
index 0 and index 1 are claims about different trips — `0030`'s own docstring says so.
`FactRepository.append_version` then resolved the `CaseFact` by `(case_id, fact_type)`
and threw the index away. Confirming the second journey appended a version to the *same*
fact and moved `current_version_id`, so the first journey's confirmed date stopped being
the case's answer. Two bookings in one case did the same to each other.

Nothing failed. It is a legitimate-looking supersede chain, and the case's answer for
"when did you leave" became whichever claim happened to be reviewed last.

`scope_key` is empty for a case-level fact and `"<evidence_item_id>:<journey_index>"`
for a travel one — scoped to the document rather than to the trip, because deciding that
two bookings describe the *same* trip is conflict detection (slice 4), not identity.
Until then each document's reading is its own fact: a duplicate to reconcile is the
conservative failure, a value silently replaced is not.

**2. `case_facts` had no unique key at all**, so a race did not collide, it forked. Two
concurrent reviews of one claim both read `PENDING_REVIEW` under READ COMMITTED, both
created a `CaseFact` of the same type, and each got its own version 1 with its own
value. `current_for_case` then returned both — two different trusted answers for one
field, with no error anywhere.

**3. `claim_review_decisions.claim_revision` promised optimistic concurrency and had
none.** Nothing compared it, `extracted_claims` has no revision column, and no client
could have sent a meaningful value. Renamed to `decision_sequence` and constrained to
what §10 actually says: a claim is decided once. The serialisation is the row lock in
`review()`; this is the constraint that makes a lost race an error instead of a second
fact.

Safe as a data migration because `AWAITING_CONFIRMATION` has only just acquired a
producer: no deployed environment holds a `case_facts` row.

Revision ID: 0033_fact_scope
Revises: 0032_claim_fact_immutability
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_fact_scope"
down_revision: str | None = "0032_claim_fact_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"


def upgrade() -> None:
    op.add_column(
        "case_facts",
        sa.Column("scope_key", sa.String(80), nullable=False, server_default=""),
    )
    op.create_unique_constraint(
        "uq_case_facts_identity", "case_facts", ["case_id", "fact_type", "scope_key"]
    )

    op.alter_column("claim_review_decisions", "claim_revision", new_column_name="decision_sequence")
    op.alter_column("claim_review_decisions", "decision_sequence", server_default="1")
    op.create_unique_constraint(
        "uq_claim_review_decisions_claim", "claim_review_decisions", ["claim_id"]
    )

    # `0032` revoked UPDATE on `case_facts`? No — it left the full grant, because
    # `current_version_id` and `revision` are what that table exists to move. `scope_key`
    # joins the columns a request may write, and that is correct: it is set once at
    # insert, and the unique constraint above is what stops it being used to smuggle one
    # fact's versions onto another. Recorded here so the next person reading `0032`'s
    # careful narrowing does not assume this table was an oversight.


def downgrade() -> None:
    op.drop_constraint("uq_claim_review_decisions_claim", "claim_review_decisions", type_="unique")
    op.alter_column("claim_review_decisions", "decision_sequence", server_default="0")
    op.alter_column("claim_review_decisions", "decision_sequence", new_column_name="claim_revision")
    op.drop_constraint("uq_case_facts_identity", "case_facts", type_="unique")
    op.drop_column("case_facts", "scope_key")
