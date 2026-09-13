"""What case deletion needs that a tenant-scoped connection cannot do

`evidence_owner` (0017) exists because a worker task resolving a tenant has no tenant to
be policed by. Case deletion has the same problem and cannot use the same function: the
purge is handed a **case** id, and by the time it runs the case may have no evidence rows
left to join through — a case whose documents were all deleted individually would resolve
to nothing and the purge would report the case absent and return successfully. That is the
`EvidenceNoLongerPresent` failure shape 0017 was written to prevent, one aggregate up.

Deliberately still two functions rather than one generalised one. Each takes the id its
caller actually holds, and neither can be induced to answer a question about the other's
aggregate. An oracle is a thing to keep small, not to make reusable.

Two more functions, for the two writes the purge makes that `app_rls` must not be able to
make generally.

**`case_scrub_model_run_hashes`.** `model_runs` is granted `INSERT, SELECT` and no `UPDATE`,
deliberately: provider telemetry is append-only and nothing in the request path should be
able to rewrite it. But §51.2 step 6 requires the `output_hash` of a destroyed document's
runs to go — it is a fingerprint, and retaining it would let anyone with database access
confirm a specific model output had been produced here. Granting `app_rls` UPDATE on
`model_runs` to serve one purge would widen every request handler's privilege for the sake
of a single statement.

**`case_release_ownership`.** This one is not about grants but about RLS itself, and the
reason is worth stating plainly: the policy on `cases` is `owner_user_id = current_setting
('app.user_id')`, as both `USING` and `WITH CHECK`. A tenant-scoped connection therefore
*cannot* set that column to anything but its own value — the row's ownership is what the
policy is made of, so releasing ownership is necessarily a privileged act. Without this, the
tombstone Domain §7.4 calls "a minimal non-identifying deletion audit" would keep the
identifier of the person who asked to be forgotten.

Kept as two functions rather than one, each taking a case id and doing one thing, because
they are called at different moments: the hashes must go *before* `extraction_runs` is
deleted (that table is the only route to them), and ownership must be released *after*
everything else, since clearing it makes the row invisible to the tenant doing the work.

Everything 0017 says about `SECURITY DEFINER` applies unchanged: `SET search_path = public`
so unqualified names cannot be shadowed by a schema earlier in the caller's path, and
`EXECUTE` revoked from PUBLIC before being granted to the application role alone. Neither
new function is an oracle — they return a count and nothing — and neither can reach a case
other than the one named, which is the same bound `case_owner` has.

Revision ID: 0036_case_owner_function
Revises: 0035_residence_totals_v1_1
Create Date: 2026-09-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0036_case_owner_function"
down_revision: str | None = "0035_residence_totals_v1_1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION case_owner(p_case_id uuid)
        RETURNS TABLE (owner_user_id varchar, case_id uuid, lifecycle_status varchar)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT c.owner_user_id, c.id, c.lifecycle_status
            FROM cases c
            WHERE c.id = p_case_id
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION case_owner(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION case_owner(uuid) TO {APP_ROLE}")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION case_scrub_model_run_hashes(p_case_id uuid)
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        DECLARE scrubbed integer;
        BEGIN
            UPDATE model_runs SET output_hash = ''
            WHERE id IN (
                SELECT model_run_id FROM extraction_runs
                WHERE case_id = p_case_id AND model_run_id IS NOT NULL
            )
            AND output_hash <> '';
            GET DIAGNOSTICS scrubbed = ROW_COUNT;
            RETURN scrubbed;
        END;
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION case_scrub_model_run_hashes(uuid) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION case_scrub_model_run_hashes(uuid) TO {APP_ROLE}"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION case_release_ownership(p_case_id uuid)
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = public
        AS $$
            UPDATE cases SET owner_user_id = '', title = ''
            WHERE id = p_case_id AND lifecycle_status = 'DELETED'
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION case_release_ownership(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION case_release_ownership(uuid) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS case_release_ownership(uuid)")
    op.execute("DROP FUNCTION IF EXISTS case_scrub_model_run_hashes(uuid)")
    op.execute("DROP FUNCTION IF EXISTS case_owner(uuid)")
