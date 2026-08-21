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

# Real tables with no ORM model. `alembic_version` holds the migration head; it is not case
# data, so RLS is the wrong control — but it is also not something a request should ever
# write, which is what migration 0013 revokes and `test_catalog_grants.py` asserts.
NON_MODELLED_TABLES = frozenset({"alembic_version"})


def _foreign_keys(session: Session) -> dict[str, set[str]]:
    """`{child table: set of parent tables}`, read from `pg_constraint`."""
    rows = session.execute(
        text(
            "SELECT child.relname, parent.relname "
            "FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid "
            "JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace n ON n.oid = child.relnamespace "
            "WHERE c.contype = 'f' AND n.nspname = 'public'"
        )
    ).all()
    edges: dict[str, set[str]] = {}
    for child, parent in rows:
        edges.setdefault(child, set()).add(parent)
    return edges


def _case_scoped_tables(session: Session) -> frozenset[str]:
    """Every table whose rows belong to one case. Two ways in: a foreign key chain rooted at
    `cases` (which is how the version tables qualify — they hold no `case_id` of their own),
    or a `case_id` column with no foreign key behind it (which is how `audit_entries`
    qualifies).

    Read from the database, not from `Base.metadata`. A metadata-derived rule is only as
    wide as the ORM: `alembic_version` has no model, which is how it kept full DML for
    `app_rls` through migration 0012 with nothing noticing. A table Postgres knows about and
    Python does not is exactly the case a defence-in-depth check must still see."""
    edges = _foreign_keys(session)
    reachable = {"cases"}
    changed = True
    while changed:  # transitive closure; the schema is small enough for the naive loop
        changed = False
        for child, parents in edges.items():
            if child not in reachable and parents & reachable:
                reachable.add(child)
                changed = True
    by_column = {
        name
        for (name,) in session.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'case_id'"
            )
        ).all()
    }
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
    expected = _case_scoped_tables(db_session) - UNPROTECTED_INFRASTRUCTURE

    missing = sorted(t for t in expected if not security.get(t, (False, False))[0])
    assert missing == [], f"case-scoped tables without RLS enabled: {missing}"

    unforced = sorted(t for t in expected if not security.get(t, (False, False))[1])
    assert unforced == [], (
        f"case-scoped tables without FORCE: {unforced}. Policies still apply to app_rls, "
        "so no behavioural test would catch this — but the owner connection would bypass "
        "them, which is the whole backstop"
    )


def test_every_case_scoped_table_has_a_tenant_policy(db_session: Session) -> None:
    expected = _case_scoped_tables(db_session) - UNPROTECTED_INFRASTRUCTURE
    missing = sorted(expected - _policied_tables(db_session))
    assert missing == [], (
        f"case-scoped tables with RLS enabled but no policy: {missing}. Postgres reads "
        "that as deny-all, so this fails closed rather than leaking — but it fails closed "
        "on the owner too, and the feature stops working"
    )


def test_the_set_of_unprotected_tables_is_exactly_the_documented_lists(
    db_session: Session,
) -> None:
    """The guard on the guards. Without this, adding a table to an exclusion list to make a
    test pass is indistinguishable from deciding it does not need protection.

    The universe comes from `pg_class`, not `Base.metadata`. A metadata-derived universe
    sees only tables with an ORM model, and `alembic_version` has none — which is how it
    kept `INSERT`/`UPDATE`/`DELETE` for `app_rls` through migration 0012 without anything
    noticing. Any table Postgres knows about now has to be classified here."""
    security = _row_security(db_session)
    unprotected = {name for name, (enabled, _) in security.items() if not enabled}
    expected = GLOBAL_REFERENCE_TABLES | UNPROTECTED_INFRASTRUCTURE | NON_MODELLED_TABLES

    assert unprotected == set(expected), (
        "a table gained or lost RLS without the lists in this file being updated"
    )


def test_the_behavioural_suite_covers_every_derived_case_scoped_table(
    db_session: Session,
) -> None:
    """The join between this file and `test_rls_matrix.py`, and the reason a table added at
    M7 is genuinely covered rather than merely noticed.

    Coverage here is structural — enabled, forced, has *a* policy. It cannot tell a correct
    policy from `FOR SELECT USING (true)`, which would satisfy all three tests above while
    leaking every tenant's rows. The matrix is what would catch that, and the matrix
    parametrises over a hand-written tuple. Asserting the two sets equal is what forces a
    new table into the behavioural suite — and from there into `seeded_case`, because
    `_assert_populated` fails on a table the arrangement never reaches."""
    from .conftest import CASE_SCOPED_TABLES

    derived = _case_scoped_tables(db_session) - UNPROTECTED_INFRASTRUCTURE
    assert set(CASE_SCOPED_TABLES) == derived, (
        "the tables the matrix exercises and the tables the schema says are case-scoped "
        "have diverged; a structural policy check cannot tell a right policy from a wrong one"
    )
