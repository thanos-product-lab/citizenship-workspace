"""A narrow, explicit privilege for the one read that runs without a tenant

A worker task has no tenant until it has resolved one, and it resolves one by reading
`evidence_items → cases`. That read therefore *cannot* be policed by RLS: there is no
`app.user_id` to police it with. It worked anyway, for the wrong reason — every
environment connects as a superuser, and a superuser bypasses row-level security.

Under the dedicated non-superuser login role ADR-0006 R1 targets, the same read returns
zero rows. The task would then raise `EvidenceNoLongerPresent`, log "evidence absent" at
info level, and return successfully. Every uploaded document would sit at `UPLOADED`
forever and the logs would calmly report that the evidence was not there. The security
suite found this the moment `case_task` became drivable on its non-superuser connection.

So the privilege becomes explicit rather than accidental: one `SECURITY DEFINER`
function, taking one evidence id and returning three columns. It is an ownership oracle
by construction — that is what the worker needs — so it is made as small as an oracle can
be, and `EXECUTE` is granted to the application role alone rather than to `PUBLIC`.

`SET search_path = public` is not decoration. Without it a `SECURITY DEFINER` function
resolves unqualified names against the *caller's* search path, so anyone able to create a
schema earlier in that path could shadow `cases` and have the definer's rights run their
table instead.

Revision ID: 0017_evidence_owner_function
Revises: 0016_evidence_processing_runs
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017_evidence_owner_function"
down_revision: str | None = "0016_evidence_processing_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "app_rls"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION evidence_owner(p_evidence_id uuid)
        RETURNS TABLE (owner_user_id varchar, case_id uuid, lifecycle_status varchar)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT c.owner_user_id, c.id, c.lifecycle_status
            FROM evidence_items e
            JOIN cases c ON c.id = e.case_id
            WHERE e.id = p_evidence_id
        $$;
        """
    )
    # Definer's rights plus a default grant to PUBLIC would hand this to every role in
    # the database. Revoke first, then grant to the one role that needs it.
    op.execute("REVOKE ALL ON FUNCTION evidence_owner(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION evidence_owner(uuid) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS evidence_owner(uuid)")
