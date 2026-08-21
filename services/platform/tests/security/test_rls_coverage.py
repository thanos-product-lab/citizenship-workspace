"""What the catalog says, rather than what a policy does — the half `test_rls_matrix.py`
structurally cannot see.

Two things live here because behaviour tests cannot reach them:

1. **`FORCE`.** A policy applies to a non-owner role whether or not the table is forced,
   so `ALTER TABLE ... NO FORCE` leaves every behavioural test green. FORCE is what makes
   policies apply to the *table owner* — which is the role a query that forgot
   `set_tenant` runs as. Without it, the fail-closed guarantee ADR-0006 rests on is not
   there, and nothing else would notice.

2. **A table nobody wrote a test for.** The matrix covers the thirteen tables it names.
   A fourteenth added in a later milestone — `evidence_items` at M7 — would be covered by
   neither until someone remembered. This file derives the set from the schema instead:
   anything reachable from `cases` by foreign key, or carrying a `case_id` column, is
   case-scoped and must be protected. A new evidence table without a policy turns this
   red on the migration that creates it.

The two exclusion lists are kept apart because they mean opposite things. Global
reference data *should not* have RLS — it has no tenant dimension, and a policy on it
would be a bug. The infrastructure tables *should* and do not; that is ADR-0006 R3, an
open gap, recorded here as an assertion rather than as prose in a document.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.shared.db import Base

pytestmark = pytest.mark.integration

# No tenant dimension: the requirement catalog and rule graph are the same rows for every
# user. RLS on these would be wrong, not missing.
GLOBAL_REFERENCE_TABLES = frozenset(
    {
        "requirement_definitions",
        "rule_versions",
        "rule_dependency_definitions",
        "rule_composition_edges",
    }
)

# ADR-0006 R3, carried since M2: the unit of work's three sinks have no policy. Two of
# them (`domain_events`, `outbox_events`) key on `aggregate_id` rather than `case_id`, so
# a policy needs a different predicate; `audit_entries` has a `case_id` and simply never
# got one. Listed rather than silently excluded, so closing the gap means deleting a name
# here and watching this file tell you to.
UNPROTECTED_INFRASTRUCTURE = frozenset({"domain_events", "audit_entries", "outbox_events"})


def _case_scoped_tables() -> frozenset[str]:
    """Every table whose rows belong to one case, derived from the schema rather than
    listed. Two ways in: a foreign key chain rooted at `cases` (which is how the version
    tables qualify — they hold no `case_id` of their own), or a `case_id` column with no
    foreign key behind it (which is how `audit_entries` qualifies)."""
    reachable = {"cases"}
    changed = True
    while changed:  # transitive closure; the schema is small enough for the naive loop
        changed = False
        for table in Base.metadata.tables.values():
            if table.name in reachable:
                continue
            parents = {
                foreign_key.column.table.name
                for column in table.c
                for foreign_key in column.foreign_keys
            }
            if parents & reachable:
                reachable.add(table.name)
                changed = True
    by_column = {t.name for t in Base.metadata.tables.values() if "case_id" in t.c}
    return frozenset(reachable | by_column)


def _row_security(session: Session) -> dict[str, tuple[bool, bool]]:
    rows = session.execute(
        text(
            "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
            "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind = 'r'"
        )
    ).all()
    return {name: (enabled, forced) for name, enabled, forced in rows}


def _policied_tables(session: Session) -> set[str]:
    return {
        name
        for (name,) in session.execute(
            text("SELECT DISTINCT tablename FROM pg_policies WHERE schemaname = 'public'")
        ).all()
    }


def test_every_case_scoped_table_has_row_level_security_enabled_and_forced(
    db_session: Session,
) -> None:
    security = _row_security(db_session)
    expected = _case_scoped_tables() - UNPROTECTED_INFRASTRUCTURE

    missing = sorted(t for t in expected if not security.get(t, (False, False))[0])
    assert missing == [], f"case-scoped tables without RLS enabled: {missing}"

    unforced = sorted(t for t in expected if not security.get(t, (False, False))[1])
    assert unforced == [], (
        f"case-scoped tables without FORCE: {unforced}. Policies still apply to app_rls, "
        "so no behavioural test would catch this — but the owner connection would bypass "
        "them, which is the whole backstop"
    )


def test_every_case_scoped_table_has_a_tenant_policy(db_session: Session) -> None:
    expected = _case_scoped_tables() - UNPROTECTED_INFRASTRUCTURE
    missing = sorted(expected - _policied_tables(db_session))
    assert missing == [], (
        f"case-scoped tables with RLS enabled but no policy: {missing}. Postgres reads "
        "that as deny-all, so this fails closed rather than leaking — but it fails closed "
        "on the owner too, and the feature stops working"
    )


def test_the_set_of_unprotected_tables_is_exactly_the_two_documented_lists(
    db_session: Session,
) -> None:
    """The guard on the guards. Without this, adding a table to an exclusion list to make
    a test pass is indistinguishable from deciding it does not need protection."""
    security = _row_security(db_session)
    modelled = {t.name for t in Base.metadata.tables.values()}
    unprotected = {name for name in modelled if not security.get(name, (False, False))[0]}

    assert unprotected == set(GLOBAL_REFERENCE_TABLES | UNPROTECTED_INFRASTRUCTURE), (
        "a table gained or lost RLS without the lists in this file being updated"
    )
