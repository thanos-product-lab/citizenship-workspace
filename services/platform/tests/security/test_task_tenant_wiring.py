"""Every Celery task establishes a tenant before it touches case data, or is named.

`test_tenant_wiring.py` walks HTTP routes. Tasks have no equivalent, and they are the
harder case: a route has `require_case_access` in its signature where a reviewer will see
it, while a task has a function and a message. Nothing about a task's shape makes the
absence of a tenant visible.

Built to the same pattern as the route file, including the lessons that file learned the
expensive way:

- inverted, so a new task is covered by default and an exemption is a visible diff;
- a coverage guard, so the assertion cannot pass by checking nothing;
- a *necessity* guard, so an exemption that is not needed cannot sit there absolving a
  future regression;
- and a **behavioural** test on the non-superuser connection, because a static check
  cannot tell a task that establishes the right tenant from one that establishes any
  tenant at all.

That last one matters most here. The static check reads an attribute the decorator
stamps; an attribute is a claim. The behavioural test is what makes it a fact.
"""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

# Imported for its registration side effect. Celery's `include=[...]` only loads task
# modules when a *worker* boots, so in a test process the registry is empty without this
# — and an empty registry would make every assertion below pass while checking nothing.
# `test_the_check_has_tasks_to_check` caught exactly that when this file was written.
import worker.tasks  # noqa: F401
from worker.celery_app import celery_app
from worker.context import TENANT_SCOPED_ATTR

pytestmark = pytest.mark.integration

Api = Callable[[str], TestClient]

#: Tasks that legitimately never enter a tenant context, each with the reason.
#:
#: The relay is the only one that can ever belong here on purpose: it is infrastructure
#: and must see every case, which is exactly why it does nothing but dispatch — it reads
#: no domain row and touches no storage. Anything that reads case data and appears in
#: this list is a bug in the list.
TENANT_FREE_TASKS: frozenset[str] = frozenset(
    {
        # Connectivity only; touches nothing.
        "worker.ping",
        # Reads `outbox_events`, which is not case-scoped, and forwards identifiers.
        "worker.outbox.relay",
    }
)


def _registered_tasks() -> list[str]:
    return [name for name in celery_app.tasks if not name.startswith("celery.")]


def test_every_task_enters_a_tenant_or_is_allowlisted() -> None:
    offenders = sorted(
        name
        for name in _registered_tasks()
        if name not in TENANT_FREE_TASKS
        and not getattr(celery_app.tasks[name], TENANT_SCOPED_ATTR, False)
    )
    assert offenders == [], (
        f"tasks that never enter the RLS tenant context: {offenders}. Build them with "
        "`case_task`, or — if the task genuinely touches no case-scoped row — add it to "
        "TENANT_FREE_TASKS with the reason."
    )


def test_the_check_has_tasks_to_check() -> None:
    """Guard against the registry being empty because `worker.tasks` was never imported,
    which would make the assertion above pass while checking nothing. The lesson of
    `test_the_check_has_routes_to_check`, on a different registry."""
    assert len(_registered_tasks()) >= 3


def test_the_allowlist_names_only_tasks_that_exist() -> None:
    stale = sorted(TENANT_FREE_TASKS - set(_registered_tasks()))
    assert stale == [], f"TENANT_FREE_TASKS names tasks that no longer exist: {stale}"


def test_the_allowlist_names_only_tasks_that_need_it() -> None:
    """An unnecessary exemption is worse than a stale one: it absolves a future rewiring
    in silence. The route file learned this by exempting the two routes that read and
    write the ownership table."""
    unnecessary = sorted(
        name
        for name in TENANT_FREE_TASKS
        if getattr(celery_app.tasks.get(name), TENANT_SCOPED_ATTR, False)
    )
    assert unnecessary == [], (
        f"tasks exempted from the tenant check that already establish one: {unnecessary}"
    )


@pytest.mark.parametrize("task_name", ["worker.evidence.validate"])
def test_a_known_case_scoped_task_is_seen_by_the_check(task_name: str) -> None:
    """A named task, so a refactor that drops the decorator is visible here rather than
    only in the behavioural test below."""
    assert task_name in _registered_tasks()
    assert getattr(celery_app.tasks[task_name], TENANT_SCOPED_ATTR, False)


# --- behavioural: the tenant is real, not just claimed --------------------------------


def _case_with_evidence(api: Api, user: str) -> tuple[uuid.UUID, uuid.UUID]:
    from app.core.storage import InMemoryStorage, get_storage
    from tests.security.conftest import SUPPORTED_ANSWERS

    case_id = str(api(user).post("/api/v1/cases", json={"title": "Tenant probe"}).json()["id"])
    api(user).put(f"/api/v1/cases/{case_id}/route-profile", json=SUPPORTED_ANSWERS)
    api(user).post(f"/api/v1/cases/{case_id}/route-profile/confirm", json={})

    grant = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence/uploads",
            json={"media_type": "application/pdf", "declared_size_bytes": 32},
        )
        .json()
    )
    store = get_storage()
    assert isinstance(store, InMemoryStorage)
    store.put(str(grant["upload_fields"]["key"]), b"%PDF-1.7 synthetic")

    item = (
        api(user)
        .post(
            f"/api/v1/cases/{case_id}/evidence",
            json={
                "upload_token": grant["upload_token"],
                "category": "TRAVEL_SUPPORT",
                "display_name": "Probe document",
                "original_filename": "probe.pdf",
            },
        )
        .json()
    )
    return uuid.UUID(case_id), uuid.UUID(item["id"])


def test_a_task_resolves_its_tenant_from_the_database_not_its_arguments(
    api: Api, db_session: Session
) -> None:
    """The property the whole design turns on.

    The task is given an evidence id and nothing else — no user, no case, no storage key.
    It must arrive at the right tenant anyway, by reading
    `evidence_items.case_id → cases.owner_user_id`, a row written by a command that had
    already passed `require_case_access`.
    """
    from worker.context import resolve_evidence_owner

    _, evidence_item_id = _case_with_evidence(api, "user_a")
    db_session.commit()

    owner, case_id, lifecycle = resolve_evidence_owner(db_session, evidence_item_id)

    assert owner == "user_a"
    assert lifecycle == "ACTIVE"
    assert case_id is not None


def test_the_resolution_refuses_an_evidence_id_that_does_not_exist(
    db_session: Session,
) -> None:
    from worker.context import EvidenceNoLongerPresent, resolve_evidence_owner

    with pytest.raises(EvidenceNoLongerPresent):
        resolve_evidence_owner(db_session, uuid.uuid4())


def test_a_task_whose_case_is_being_deleted_stops_rather_than_failing(
    api: Api, db_session: Session
) -> None:
    """A deleted case is not a processing failure.

    `CaseNoLongerWritable` rather than an exception Celery would retry: no number of
    attempts makes a deleted case writable, and a FAILED run opens a PROCESSING_FAILURE
    issue (ADR-0016) telling the user their document could not be processed when what
    happened is that they deleted the case.
    """
    from worker.context import CaseNoLongerWritable, case_task

    case_id, evidence_item_id = _case_with_evidence(api, "user_a")
    api("user_a").delete(f"/api/v1/cases/{case_id}")
    db_session.commit()

    with pytest.raises(CaseNoLongerWritable) as stopped, case_task(evidence_item_id):
        pass
    assert stopped.value.lifecycle_status == "DELETION_PENDING"


def test_case_task_puts_the_resolved_owner_on_the_session(
    api: Api, db_session: Session, rls_sessionmaker: sessionmaker[Session]
) -> None:
    """The assertion that kills the mutation.

    The first version of this file never called `case_task` at all — it opened its own
    session, called `set_tenant` by hand and counted rows, which is what
    `test_rls_matrix.py` already does. A reviewer neutralised `set_tenant` inside
    `worker.context` and **all ten tests in this file passed**, along with the rest of
    the security suite. The docstring claimed to express the gate's mutation as a
    standing test; it expressed an RLS test wearing a task's name.

    This drives the real wrapper and reads what it actually bound, on the non-superuser
    connection where a missing tenant fails closed rather than being invisible.
    """
    from app.shared.tenant import TENANT_SESSION_KEY
    from worker.context import case_task

    _, evidence_item_id = _case_with_evidence(api, "user_a")
    db_session.commit()

    with case_task(evidence_item_id, sessions=rls_sessionmaker) as ctx:
        assert ctx.owner_user_id == "user_a"
        assert ctx.session.info.get(TENANT_SESSION_KEY) == "user_a"


def test_the_tenant_case_task_establishes_is_the_one_the_policies_see(
    api: Api, db_session: Session, rls_sessionmaker: sessionmaker[Session]
) -> None:
    """`session.info` is a record of intent; this is whether the database agrees.

    On the non-superuser connection, a context whose tenant never reached the GUC sees
    nothing — so the row being visible is the tenant being real. Delete `set_tenant`
    from `case_task` and this goes red where the static attribute check cannot.
    """
    from worker.context import case_task

    _, evidence_item_id = _case_with_evidence(api, "user_a")
    db_session.commit()

    with case_task(evidence_item_id, sessions=rls_sessionmaker) as ctx:
        visible = ctx.session.execute(
            text("SELECT count(*) FROM evidence_items WHERE id = :i"),
            {"i": evidence_item_id},
        ).scalar_one()
        assert visible == 1, (
            "the task's own session cannot see the document it was given — the tenant "
            "was never established, and on the superuser connection this would pass"
        )


def test_a_task_context_cannot_reach_another_users_evidence(
    api: Api, db_session: Session, rls_sessionmaker: sessionmaker[Session]
) -> None:
    """The boundary, from inside the wrapper rather than beside it."""
    from worker.context import case_task

    _, mine = _case_with_evidence(api, "user_a")
    _, theirs = _case_with_evidence(api, "user_b")
    db_session.commit()

    with case_task(mine, sessions=rls_sessionmaker) as ctx:
        others = ctx.session.execute(
            text("SELECT count(*) FROM evidence_items WHERE id = :i"), {"i": theirs}
        ).scalar_one()
        assert others == 0


def test_a_task_context_cannot_write_against_another_users_evidence(
    api: Api, db_session: Session, rls_sessionmaker: sessionmaker[Session]
) -> None:
    """A write against another tenant's row changes nothing.

    It does not *raise*, and expecting it to was wrong: the policy's `USING` clause
    filters the row out of the statement's scope, so the `UPDATE` matches zero rows and
    reports success. `WITH CHECK` is what raises, and it fires on a row being written
    *into* a tenant the writer does not own — which this policy, predicated on ownership
    rather than on any mutable column, cannot be steered into via an UPDATE.

    Silent-zero-rows is the right behaviour and the more important one to pin: a task
    that resolved the wrong tenant does not corrupt another user's document, it simply
    accomplishes nothing.
    """
    from worker.context import case_task

    _, mine = _case_with_evidence(api, "user_a")
    _, theirs = _case_with_evidence(api, "user_b")
    db_session.commit()

    with case_task(mine, sessions=rls_sessionmaker) as ctx:
        ctx.session.execute(
            text("UPDATE evidence_items SET processing_status = 'FAILED' WHERE id = :i"),
            {"i": theirs},
        )
        ctx.session.commit()

    # And the other user's document is untouched.
    survived = db_session.execute(
        text("SELECT processing_status FROM evidence_items WHERE id = :i"), {"i": theirs}
    ).scalar_one()
    assert survived != "FAILED"


def test_a_tenantless_session_sees_no_evidence_at_all(
    api: Api, db_session: Session, rls_sessionmaker: sessionmaker[Session]
) -> None:
    """Fail closed: a session with no tenant yields nothing, not everything.

    This is a property of the *policies*, not of `case_task` — the tests above are what
    exercise the wrapper. Kept because it is the premise the others rest on: if a
    tenantless session could read, none of them would mean anything.
    """
    _case_with_evidence(api, "user_a")
    db_session.commit()

    with rls_sessionmaker() as session:
        count = session.execute(text("SELECT count(*) FROM evidence_items")).scalar_one()
    assert count == 0
