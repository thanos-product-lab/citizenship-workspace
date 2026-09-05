"""Take back UPDATE on the rows that are supposed to be a record

`0030` created five tables and granted `SELECT, INSERT, UPDATE, DELETE` on all of them in
one loop. Three of the five are records of something that happened, and a record a
request path can rewrite is not a record — the argument `0026_model_runs_append_only`
makes about provenance, applied one milestone later to the tables where it matters most.

**`claim_review_decisions` — no UPDATE at all.** This table *is* prime directive 1: the
row that separates what a model proposed from what a human decided. `service.review()`
inserts one and never touches it again, and `ClaimRepository` exposes no mutator. Both
were convention. If this row can be edited, then "a trusted fact exists only because a
human decided" is a sentence in a docstring rather than a property of the database.
Nothing about a past decision is redactable, either — but not for the reason first
written here, which was that the row "holds the user's own corrected value". That is true
on the blind path and false on the prefilled one: a `PREFILLED` confirm writes
`proposal.raw`, the model's transcription of the document, and the user typed nothing.
Both M8 slice-3a reviews caught it independently.

The revoke still stands, on the narrower and correct ground: a decision is a record of
something a person did, and a record that can be edited is not one. What it retains
alongside the fact is deliberate under RFC §39 — deleting evidence does not delete a
confirmed fact — and `DELETE` stays granted so M11 case deletion can still remove the row
entirely. If a prefilled confirm's `corrected_raw` should be redactable on *evidence*
deletion, that needs a column-level `GRANT UPDATE` in a new migration and a decision
recorded here first.

**`fact_versions` — no UPDATE at all.** Append-only by construction:
`FactRepository.append_version` writes a new row and moves `case_facts.current_version_id`,
leaving the previous version untouched so a historical assessment keeps resolving to the
exact value it read (CLAUDE.md §2.3). The grant made that a convention too.

**`extracted_claims` — UPDATE on six named columns.** A claim is immutable *as a
proposal*: `proposed_raw` has no setter and correcting a claim writes to the decision,
which is CLAUDE.md §9's *"correcting a claim preserves the original proposal"*. But two
things legitimately change on the row — its `status` as it is reviewed, superseded or
invalidated, and its content when the document behind it is destroyed.

So the same column-level grant `0028` used for `extraction_runs`, and for the same
reason: redactable-but-not-rewritable is a real rule, and a blanket revoke would state a
different, false one. `case_id`, the evidence and run ids, `claim_type`,
`journey_index`, `value_schema_version`, `model_confidence` and `created_at` are what a
claim *is* — which run read which field of which document, and how sure it said it was —
and none of them may be rewritten by anything.

**`fact_evidence_links` — UPDATE on two.** A link is withdrawn, never repointed. Which
fact rests on which document is the provenance; `availability_status` and `withdrawn_at`
are its state.

`case_facts` keeps a full grant: `current_version_id` and `revision` are exactly what it
exists to move.

DELETE is left alone throughout. Case deletion (Domain §51.2, M11) removes every
case-scoped row, and narrowing that is that milestone's decision to make.

Revision ID: 0032_claim_fact_immutability
Revises: 0031_run_category_scope
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0032_claim_fact_immutability"
down_revision: str | None = "0031_run_category_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"

#: Tables that are a record of a past event. Nothing may rewrite them.
_APPEND_ONLY = ("claim_review_decisions", "fact_versions")

#: Tables where a named few columns are state, and the rest are identity.
_NARROWED = {
    # Status as the claim is reviewed/superseded/invalidated; the rest is redaction the
    # purge is obliged to perform (`ExtractedClaim.redact`).
    "extracted_claims": (
        "status",
        "superseded_by_claim_id",
        "proposed_raw",
        "proposed_iso",
        "normalised_value",
        "source_locator",
    ),
    "fact_evidence_links": ("availability_status", "withdrawn_at"),
}


def upgrade() -> None:
    for table in _APPEND_ONLY:
        op.execute(f"REVOKE UPDATE ON {table} FROM {APP_ROLE}")
    for table, columns in _NARROWED.items():
        op.execute(f"REVOKE UPDATE ON {table} FROM {APP_ROLE}")
        op.execute(f"GRANT UPDATE ({', '.join(columns)}) ON {table} TO {APP_ROLE}")


def downgrade() -> None:
    for table in (*_APPEND_ONLY, *_NARROWED):
        op.execute(f"GRANT UPDATE ON {table} TO {APP_ROLE}")
