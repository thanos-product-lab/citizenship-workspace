"""extraction_runs: revoke UPDATE, and predicate the policy on the column that is queried

Two corrections from the M8 slice 2 reviews, both of which are a lesson from an earlier
migration not carried one step forward.

**1. `UPDATE` was granted to the request role, on every column.**
`0026_model_runs_append_only` exists for one purpose — taking that privilege back off
`model_runs`, because *"provenance a request path can rewrite is not provenance"*. `0027`
then granted it on `extraction_runs` the very next migration. `ExtractionRun` is written
once by `record()`, has no `start()`/
`finish()` pair, and `ExtractionRunRepository` deliberately exposes no mutator; all three
were convention, and the grant undid them.

The revoke is *column-level*, not total, because a blanket one collides with the other
half of this fix: evidence deletion has to clear `input_hash` and
`classification_reasoning`, and the purge runs as `app_rls` like every other case-scoped
write. Granting `UPDATE` on exactly those two columns states the real rule — the request
role may redact what deletion obliges it to erase, and may not rewrite what a run
concluded, when, at what cost, or under which model.

**2. The policy read a different column than the code does.** `0027` predicated through
`evidence_items`, copying the grandchild shape used by `evidence_files` and
`evidence_processing_runs`. But those tables carry no `case_id` of their own, and
`extraction_runs` does — and `ExtractionRunRepository.latest_classifications_for_case`
filters on it. So the row-level guarantee was over one column while every query was over
another, with nothing tying the two together.

The established pattern for a table that carries its own `case_id` is
`0021_evidence_travel_links`, which predicates on that column directly. This adopts it,
and adds a composite foreign key so the two columns cannot diverge in the first place:
`(evidence_item_id, case_id)` must name a real pairing in `evidence_items`.

Not exploitable as it stood — nothing user-supplied writes `case_id`, and a cross-tenant
read needed both columns to be wrong at once. This is defence in depth being restored to
depth, which is the only condition in which it is worth having.

Revision ID: 0028_extraction_runs_hardening
Revises: 0027_extraction_runs
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_extraction_runs_hardening"
down_revision: str | None = "0027_extraction_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"
_TENANT = "current_setting('app.user_id', true)"
_TABLE = "extraction_runs"

#: Predicated on this table's own `case_id`, the way `0021_evidence_travel_links` does for
#: the same reason: it is the column the queries filter on.
_PREDICATE = (
    f"EXISTS (SELECT 1 FROM cases c WHERE c.id = {_TABLE}.case_id "
    f"AND c.owner_user_id = {_TENANT})"
)
_OLD_PREDICATE = (
    "EXISTS (SELECT 1 FROM evidence_items e JOIN cases c ON c.id = e.case_id "
    f"WHERE e.id = {_TABLE}.evidence_item_id AND c.owner_user_id = {_TENANT})"
)


def upgrade() -> None:
    op.execute(f"REVOKE UPDATE ON {_TABLE} FROM {APP_ROLE}")
    # ...except the two columns that exist in order to be erasable.
    #
    # A blanket revoke and the deletion path are both right and they collide: evidence
    # deletion must clear `input_hash` (a content fingerprint) and
    # `classification_reasoning` (model prose that may quote the document), and the purge
    # runs as `app_rls` like every other case-scoped write.
    #
    # A column-level grant says the actual rule rather than picking one of the two. The
    # request role may redact what deletion is obliged to erase, and may not rewrite what
    # the run concluded, when, at what cost, or under which model — which is the
    # provenance the revoke was protecting.
    op.execute(
        f"GRANT UPDATE (input_hash, classification_reasoning) ON {_TABLE} TO {APP_ROLE}"
    )

    # The two columns can no longer disagree: a run must name an item that really does
    # belong to the case the run claims. Requires a unique key on the pair it references.
    op.create_unique_constraint(
        "uq_evidence_items_id_case_id", "evidence_items", ["id", "case_id"]
    )
    op.create_foreign_key(
        "fk_extraction_runs_item_belongs_to_case",
        _TABLE,
        "evidence_items",
        ["evidence_item_id", "case_id"],
        ["id", "case_id"],
    )

    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant ON {_TABLE}")
    op.execute(
        f"CREATE POLICY {_TABLE}_tenant ON {_TABLE} "
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant ON {_TABLE}")
    op.execute(
        f"CREATE POLICY {_TABLE}_tenant ON {_TABLE} "
        f"FOR ALL USING ({_OLD_PREDICATE}) WITH CHECK ({_OLD_PREDICATE})"
    )
    op.drop_constraint("fk_extraction_runs_item_belongs_to_case", _TABLE, type_="foreignkey")
    op.drop_constraint("uq_evidence_items_id_case_id", "evidence_items", type_="unique")
    op.execute(f"GRANT UPDATE ON {_TABLE} TO {APP_ROLE}")
