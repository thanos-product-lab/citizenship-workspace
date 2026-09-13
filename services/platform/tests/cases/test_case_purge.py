"""Complete case deletion, end to end (Domain §51.2, threat model §19).

`test_deletion.py` covers the synchronous half — the case enters `DELETION_PENDING`, writes
stop, the purge is queued. This covers the half that did not exist until the release slice:
the purge itself. Until then `CaseDeletionRequested` sat in `NO_CONSUMER`, so a deleted case
was a case its owner could no longer see, with every row and every object still in place.

The assertion that matters most is `test_every_case_scoped_table_is_purged`. `_DELETION_ORDER`
is a hand-written list so a reviewer can read what gets destroyed, and a hand-written list is
exactly how a table added in a later milestone is silently missed. So the list is checked
against the live schema the same way `tests/security/test_rls_coverage.py` checks policies:
derive the truth from Postgres, and fail on the migration that introduces a table nobody
added here.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.assessments import service as assessments_service
from app.cases.domain import ApplicationCase, LifecycleStatus
from app.cases.purge import _DELETION_ORDER, purge_case
from app.core.storage import get_storage
from app.seed.demo_case import seed_demo_case
from app.shared.errors import IllegalTransition
from app.shared.tenant import clear_tenant, set_tenant
from tests.conftest import as_user

pytestmark = pytest.mark.integration

# Mirrors `test_rls_coverage.py`. These carry no case dimension, so they are not case-scoped
# and must not be purged: the requirement catalog and rule graph are the same rows for every
# user, and `model_runs` / `ai_daily_spend` are deployment-wide telemetry (migration 0025).
# `model_runs.output_hash` *is* scrubbed by the purge — the row survives, the fingerprint
# does not — which is a different operation from deleting it and is asserted separately.
NOT_CASE_SCOPED = frozenset(
    {
        "requirement_definitions",
        "rule_versions",
        "rule_dependency_definitions",
        "rule_composition_edges",
        "model_runs",
        "ai_daily_spend",
        "alembic_version",
        # Keyed on `aggregate_id`, not `case_id`, so they are not reachable by the
        # derivation below. Purged all the same, by `_delete_events`, and asserted in
        # `test_domain_and_outbox_events_for_the_case_are_gone`.
        "domain_events",
        "outbox_events",
    }
)


def _case_scoped_tables(session: Session) -> frozenset[str]:
    """Every table whose rows belong to one case: reachable from `cases` by a foreign-key
    chain, or carrying a `case_id` column. Read from Postgres rather than from
    `Base.metadata`, because a metadata-derived rule is only as wide as the ORM."""
    edges: dict[str, set[str]] = {}
    for child, parent in session.execute(
        text(
            "SELECT child.relname, parent.relname FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid "
            "JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace n ON n.oid = child.relnamespace "
            "WHERE c.contype = 'f' AND n.nspname = 'public'"
        )
    ).all():
        edges.setdefault(child, set()).add(parent)

    reachable = {"cases"}
    changed = True
    while changed:
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


#: Case-scoped tables this fixture leaves empty, and therefore does not prove the purge
#: clears. Named rather than left implicit, because the first version of these tests
#: measured nothing about them and read as though it measured everything: the seed alone
#: populates eleven of twenty-four tables, and a mutation blanking the predicate on an
#: empty table passes every assertion.
#:
#: What remains here is the AI and claim path, which has no synchronous producer — a
#: document reaches `extracted_claims` only through the worker, and this suite runs none.
#: Closing it means either a worker in the test path or hand-built rows in seven tables;
#: both are worth more than they cost only once there is a second consumer for them.
#: `test_the_model_run_output_hash_is_scrubbed` builds two of them by hand for its own
#: purposes and is the pattern to follow.
#:
#: Deleting a name from this list is what widening the coverage looks like.
NOT_POPULATED_BY_THE_FIXTURE = frozenset(
    {
        "evidence_file_texts",
        "fact_evidence_links",
        "fact_versions",
        "claim_review_decisions",
        "case_facts",
        "extracted_claims",
        "extraction_runs",
        "evidence_processing_runs",
    }
)


def _a_populated_case(session: Session, *, user_id: str) -> ApplicationCase:
    """Seed the canonical case and run a real assessment over it.

    Shared by the fixture and by the bystander tests, and that sharing is the point: a
    bystander built by a lesser route is a bystander with empty tables, and a wrong
    predicate on a table it does not populate destroys nothing it can notice. Three
    mutations survived on exactly that before this existed.
    """
    case_id = seed_demo_case(session, user_id=user_id)
    session.commit()
    case = session.get(ApplicationCase, case_id)
    assert case is not None
    assessments_service.recalculate(session, case=case, user=as_user(user_id))
    session.commit()
    return case


@pytest.fixture
def a_seeded_case(db_session: Session) -> ApplicationCase:
    """The canonical synthetic case, **recalculated**: twelve trips, eleven uploaded
    documents, and then a full assessment run so the results, input links and issue queue
    exist too.

    The seed is used rather than a hand-built minimum because the property under test is
    *completeness* — a fixture touching six tables would only ever prove the purge clears
    six tables. The recalculation is here for the same reason and was not in the first
    version: seeding alone leaves thirteen case-scoped tables empty, including every
    assessment table, so the completeness assertions were passing over rows that were never
    there. Mutation testing found that, not review.
    """
    return _a_populated_case(db_session, user_id="user_a")


@pytest.fixture
def a_case_pending_deletion(db_session: Session, a_seeded_case: ApplicationCase) -> ApplicationCase:
    a_seeded_case.request_deletion(at=datetime.now(UTC))
    db_session.commit()
    return a_seeded_case


def test_every_case_scoped_table_is_purged(db_session: Session) -> None:
    """The guard that makes an explicit list safe to keep."""
    named = {table for table, _ in _DELETION_ORDER}
    # `cases` is the tombstone, not a casualty — §51.2 step 8 sets it `DELETED`.
    expected = _case_scoped_tables(db_session) - NOT_CASE_SCOPED - {"cases"}

    missing = sorted(expected - named)
    assert missing == [], (
        f"case-scoped tables the purge does not delete from: {missing}. Add them to "
        "_DELETION_ORDER, children before parents, or add them to NOT_CASE_SCOPED with "
        "the reason they carry no case dimension."
    )

    unknown = sorted(named - expected)
    assert unknown == [], f"_DELETION_ORDER names tables that are not case-scoped: {unknown}"


def test_the_deletion_order_puts_children_before_parents(db_session: Session) -> None:
    """A parent deleted first would fail on a foreign key, and the purge would abandon the
    case mid-destruction. Checked against the real constraints rather than by reading."""
    position = {table: index for index, (table, _) in enumerate(_DELETION_ORDER)}
    violations = []
    for child, parent in db_session.execute(
        text(
            "SELECT child.relname, parent.relname FROM pg_constraint c "
            "JOIN pg_class child ON child.oid = c.conrelid "
            "JOIN pg_class parent ON parent.oid = c.confrelid "
            "JOIN pg_namespace n ON n.oid = child.relnamespace "
            "WHERE c.contype = 'f' AND n.nspname = 'public'"
        )
    ).all():
        if child == parent:
            continue  # self-reference: one statement deletes both ends, RI is end-of-statement
        if child in position and parent in position and position[child] > position[parent]:
            violations.append(f"{child} deleted after its parent {parent}")
    assert violations == [], violations


def test_the_purge_refuses_a_case_nobody_asked_to_delete(
    db_session: Session, a_seeded_case: ApplicationCase
) -> None:
    """The single most important refusal in this module. An ACTIVE case reaching the purge
    would be the worst bug it could have, so it returns rather than raising: no number of
    retries can make an unrequested deletion correct."""
    assert a_seeded_case.lifecycle_status is LifecycleStatus.ACTIVE

    outcome = purge_case(db_session, get_storage(), case_id=a_seeded_case.id)

    assert outcome.purged is False
    assert outcome.reason == "not_pending"
    assert outcome.rows_deleted == 0
    db_session.refresh(a_seeded_case)
    assert a_seeded_case.lifecycle_status is LifecycleStatus.ACTIVE


def test_an_absent_case_is_not_an_error(db_session: Session) -> None:
    outcome = purge_case(db_session, get_storage(), case_id=uuid.uuid4())
    assert (outcome.purged, outcome.reason) == (False, "absent")


def test_a_second_purge_finds_nothing_to_do(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """The relay is at-least-once, so redelivery is expected rather than exceptional."""
    first = purge_case(db_session, get_storage(), case_id=a_case_pending_deletion.id)
    assert first.purged is True

    second = purge_case(db_session, get_storage(), case_id=a_case_pending_deletion.id)
    assert (second.purged, second.reason) == (False, "already_purged")
    assert second.rows_deleted == 0


def test_the_case_cannot_be_marked_deleted_twice(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """Reachable only against the aggregate: the purge returns early on redelivery, so this
    guard is real and cannot be hit through the task. Same shape as `request_deletion`'s."""
    purge_case(db_session, get_storage(), case_id=a_case_pending_deletion.id)
    # No refresh: the row is ownerless now and invisible to this tenant. The aggregate in
    # memory carries the transition the purge made, which is what the guard reads.
    assert a_case_pending_deletion.lifecycle_status is LifecycleStatus.DELETED
    with pytest.raises(IllegalTransition):
        a_case_pending_deletion.mark_deleted(at=datetime.now(UTC))


def test_the_documents_are_gone_from_storage(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """§51.2 step 4, and the assertion the gate asks for by name: gone from the store, not
    merely scheduled. The keys are read before the purge because afterwards there is nothing
    left holding them."""
    storage = get_storage()
    keys = [
        row[0]
        for row in db_session.execute(
            text(
                "SELECT f.storage_key FROM evidence_files f "
                "JOIN evidence_items i ON i.id = f.evidence_item_id WHERE i.case_id = :c"
            ),
            {"c": a_case_pending_deletion.id},
        ).all()
    ]
    assert keys, "the seeded case should have uploaded documents to destroy"
    for key in keys:
        assert storage.head(key) is not None, "precondition: the object is there"

    outcome = purge_case(db_session, storage, case_id=a_case_pending_deletion.id)

    assert outcome.objects_deleted == len(keys)
    for key in keys:
        assert storage.head(key) is None, f"{key} survived the purge"


def test_no_row_in_any_case_scoped_table_survives(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """Derived, not enumerated: ask every case-scoped table whether it still holds a row for
    this case. A table added later and forgotten fails here as well as in the coverage test."""
    case_id = a_case_pending_deletion.id
    before = _rows_for_case(db_session, case_id)

    # The fixture has to actually reach the tables this claims to check, or the assertion
    # below is satisfied by absence. Checked rather than trusted, so a change that stops
    # the fixture populating something fails here instead of quietly narrowing the test.
    expected = {table for table, _ in _DELETION_ORDER} - NOT_POPULATED_BY_THE_FIXTURE
    reachable_by_case_id = expected & set(_case_id_tables(db_session))
    unpopulated = sorted(reachable_by_case_id - set(before))
    assert unpopulated == [], (
        f"the fixture no longer populates {unpopulated}, so the purge is not being tested "
        "against them. Restore the fixture, or move them to NOT_POPULATED_BY_THE_FIXTURE "
        "with the reason."
    )

    purge_case(db_session, get_storage(), case_id=case_id)

    assert _rows_for_case(db_session, case_id) == {}


def _case_id_tables(session: Session) -> list[str]:
    """Tables carrying a `case_id`, which is what `_rows_for_case` can count. The nine
    reachable only through a parent are covered by the coverage and ordering tests
    instead — there is no single column to count them by."""
    return [
        name
        for (name,) in session.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'case_id' "
                "AND table_name <> 'cases'"
            )
        ).all()
    ]


def _rows_for_case(session: Session, case_id: uuid.UUID) -> dict[str, int]:
    """Per-table counts for every table that carries a `case_id`, non-zero only."""
    counts = {}
    for (table,) in session.execute(
        text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'case_id' "
            "AND table_name <> 'cases'"
        )
    ).all():
        n = session.execute(
            text(f"SELECT count(*) FROM {table} WHERE case_id = :c"), {"c": case_id}
        ).scalar_one()
        if n:
            counts[table] = n
    return counts


def test_the_tombstone_keeps_no_name_and_no_owner(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """§51.2 step 7. The `cases` row survives as the deletion audit — and an audit that names
    the person is not the non-identifying one Domain §7.4 asks for. The seeded case's title
    carries a person's name, which is the ordinary situation rather than a contrived one."""
    case_id = a_case_pending_deletion.id
    assert a_case_pending_deletion.title
    assert a_case_pending_deletion.owner_user_id == "user_a"

    purge_case(db_session, get_storage(), case_id=case_id)

    # The former owner cannot read their own tombstone, and that is not a side effect to
    # work around — it is the strongest available statement of "non-identifying". The RLS
    # predicate is `owner_user_id = current_setting('app.user_id')`, so a row owned by
    # nobody matches nobody. Asserted before reading the row at all, because the reading
    # below has to step outside the tenant to happen.
    assert (
        db_session.execute(
            text("SELECT count(*) FROM cases WHERE id = :c"), {"c": case_id}
        ).scalar_one()
        == 0
    ), "the purged case is still visible to the tenant that owned it"

    clear_tenant(db_session)
    row = db_session.execute(
        text(
            "SELECT lifecycle_status, title, owner_user_id, route_key, deletion_requested_at "
            "FROM cases WHERE id = :c"
        ),
        {"c": case_id},
    ).one()
    lifecycle, title, owner, route_key, requested_at = row

    assert lifecycle == LifecycleStatus.DELETED.value
    assert title == ""
    assert owner == ""
    # What a deletion audit is allowed to keep: that one happened, to a case on this route,
    # and when it was asked for.
    assert route_key
    assert requested_at is not None


def test_domain_and_outbox_events_for_the_case_are_gone(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """Events key on `aggregate_id`, not `case_id`, so they are reachable only through ids
    collected before the rows holding them are deleted. They are in scope because
    `domain_events.actor_id` is the user's own identifier."""
    case_id = a_case_pending_deletion.id
    before = db_session.execute(
        text("SELECT count(*) FROM domain_events WHERE aggregate_id = :c"), {"c": case_id}
    ).scalar_one()
    assert before, "precondition: the case has its own events"

    outcome = purge_case(db_session, get_storage(), case_id=case_id)

    assert outcome.events_deleted >= before
    for table in ("domain_events", "outbox_events"):
        remaining = db_session.execute(
            text(f"SELECT count(*) FROM {table} WHERE aggregate_id = :c"), {"c": case_id}
        ).scalar_one()
        assert remaining == 0, f"{table} still holds rows for the deleted case"


def test_no_event_survives_for_any_aggregate_in_the_case(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """The half a case-id-only sweep would miss: an `EvidenceUploaded` row keys on the
    evidence item, not the case, and would otherwise outlive everything it refers to."""
    case_id = a_case_pending_deletion.id
    evidence_ids = [
        row[0]
        for row in db_session.execute(
            text("SELECT id FROM evidence_items WHERE case_id = :c"), {"c": case_id}
        ).all()
    ]
    assert evidence_ids, "precondition: the seeded case has evidence"

    purge_case(db_session, get_storage(), case_id=case_id)

    orphaned = db_session.execute(
        text("SELECT count(*) FROM domain_events WHERE aggregate_id = ANY(:ids)"),
        {"ids": evidence_ids},
    ).scalar_one()
    assert orphaned == 0


def test_the_model_run_output_hash_is_scrubbed(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """§51.2 step 6. `model_runs` has no `case_id`, so these rows are reachable only through
    `extraction_runs` — which the purge is about to delete. The row survives as deployment
    telemetry; the fingerprint of what a model said about a destroyed document does not."""
    case_id = a_case_pending_deletion.id
    # Arranged outside the tenant, because the tenant cannot arrange it: `app_rls` has no
    # UPDATE on `extraction_runs` or `model_runs` — both are append-only from the request
    # path. That is the same privilege boundary the purge has to cross, which is why it
    # crosses it through a definer function rather than a widened grant.
    clear_tenant(db_session)
    db_session.execute(
        text(
            "INSERT INTO model_runs (id, capability, provider, model, prompt_version, "
            "schema_version, status, latency_ms, attempts, output_hash, created_at) VALUES "
            "(:id, 'DocumentClassifier', 'fake', 'm', 'v1', 'v1', 'SUCCEEDED', 5, 1, :h, now())"
        ),
        {"id": (run_id := uuid.uuid4()), "h": "a" * 64},
    )
    # An extraction run for one of the case's documents. Inserted rather than produced:
    # processing is asynchronous and no worker runs in this suite, so the seeded case has
    # evidence and no runs against it yet.
    item_id, file_id = db_session.execute(
        text(
            "SELECT i.id, f.id FROM evidence_items i "
            "JOIN evidence_files f ON f.evidence_item_id = i.id "
            "WHERE i.case_id = :c LIMIT 1"
        ),
        {"c": case_id},
    ).one()
    processing_run_id = uuid.uuid4()
    db_session.execute(
        text(
            "INSERT INTO evidence_processing_runs (id, evidence_item_id, evidence_file_id, "
            "status, pipeline_version, started_at, completed_at, retry_count, idempotency_key) "
            "VALUES (:id, :i, :f, 'SUCCEEDED', 'v1', now(), now(), 0, :k)"
        ),
        {"id": processing_run_id, "i": item_id, "f": file_id, "k": str(processing_run_id)},
    )
    db_session.execute(
        text(
            "INSERT INTO extraction_runs (id, case_id, evidence_item_id, evidence_file_id, "
            "processing_run_id, model_run_id, capability, status, input_hash, "
            "input_characters, classified_category, started_at, completed_at) VALUES "
            "(:id, :c, :i, :f, :p, :r, 'DocumentClassifier', 'SUCCEEDED', :h, 100, "
            "'TRAVEL_SUPPORT', now(), now())"
        ),
        {
            "id": uuid.uuid4(),
            "c": case_id,
            "i": item_id,
            "f": file_id,
            "p": processing_run_id,
            "r": run_id,
            "h": "b" * 64,
        },
    )
    db_session.commit()

    set_tenant(db_session, "user_a")
    outcome = purge_case(db_session, get_storage(), case_id=case_id)

    assert outcome.model_runs_scrubbed == 1
    clear_tenant(db_session)
    row = db_session.execute(
        text("SELECT output_hash FROM model_runs WHERE id = :r"), {"r": run_id}
    ).first()
    assert row is not None, "the telemetry row itself is kept — only the fingerprint goes"
    assert row[0] == ""


def test_nothing_belonging_to_the_users_other_case_is_touched(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """The bystander is a **second case owned by the same user**, and that is the whole
    point of the test.

    The first version used another user's case and proved nothing: every delete runs under
    the tenant, so RLS refused to show it the other tenant's rows and the assertion held
    with `("evidence_items", "1 = 1")` substituted for the real predicate. A mutation that
    would destroy every evidence item in the database passed. Two cases under one tenant
    are visible to the same policy, so here only the `case_id` in each predicate stands
    between this purge and the user's other case — which is what twenty-four hand-written
    predicates need checking for.
    """
    other = _a_populated_case(db_session, user_id="user_a")
    other_id = other.id
    before = _rows_for_case(db_session, other_id)
    assert before, "precondition: the bystander case populates many tables"

    purge_case(db_session, get_storage(), case_id=a_case_pending_deletion.id)

    assert _rows_for_case(db_session, other_id) == before
    assert other.lifecycle_status is LifecycleStatus.ACTIVE
    assert other.owner_user_id == "user_a"
    assert other.title


def test_another_tenants_case_is_out_of_reach_entirely(
    db_session: Session, a_case_pending_deletion: ApplicationCase
) -> None:
    """The second bound, and it is not the predicate: the purge runs tenant-scoped, so RLS
    is what stops a wrong predicate reaching another user at all.

    Worth its own test because it is defence in depth actually working, and because keeping
    it separate is what stopped the test above from quietly relying on it. A purge is the
    most destructive operation in the product, and it holds the tenant throughout rather
    than escalating to the owner role — the two definer functions exist precisely so that
    the two writes needing privilege can have it without the whole operation taking it.
    """
    set_tenant(db_session, "user_b")
    other_id = _a_populated_case(db_session, user_id="user_b").id
    before = _rows_for_case(db_session, other_id)
    assert before

    set_tenant(db_session, "user_a")
    purge_case(db_session, get_storage(), case_id=a_case_pending_deletion.id)

    set_tenant(db_session, "user_b")
    assert _rows_for_case(db_session, other_id) == before
