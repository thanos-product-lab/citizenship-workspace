"""Tenant context for work that has no request around it.

A Celery task has no request scope, no `require_case_access` dependency, and no
request-scoped session. It is also inherently multi-commit: validate, extract, persist —
each plausibly its own transaction. So the question this module answers is where a
task's tenant comes from, and the answer has to survive all of that.

**ADR-0017 already did the hard half.** The tenant lives on `Session.info`, and an
`after_begin` listener registered on the `Session` *class* re-applies role and GUC
whenever a session opens a transaction — including the autobegin after every commit and
every rollback. That decision was made so the mechanism would cover "the request
session, the recalculation-failure recovery's own session, the CLI scripts and the seed"
by construction. A worker task is the fourth case and needs no new machinery: call
`set_tenant` once and every later transaction re-arms itself. Under the pre-ADR-0017
design a task's second transaction would have run tenantless, which is why M7 was
blocked on that fix.

What is *not* free is where the user id comes from.

**Not from the message.** A Celery kwarg is not an authorisation artefact. Redis is
unauthenticated in local compose and published to the host, so if the tenant travelled in
the task payload, anyone able to enqueue could set it to any user — an RLS bypass by
message forgery, defeating the entire control. Task arguments carry opaque identifiers
and nothing else.

**Not from the storage key.** Domain §52 and threat model §26: *a storage key never
grants authorisation*. A key contains a case id for operational legibility; possessing it
proves nothing. Reading the tenant out of one would make the key a credential, which is
precisely the invariant.

**From the database.** `evidence_items.case_id → cases.owner_user_id`, a row written
transactionally by a command that had already passed `require_case_access`. The
authorisation decision is *inherited from the write*, not re-made in the worker.

That resolution is the sharp edge and should be read as one: it is the only place in the
system that reads case rows with no policy behind it. It is one function, reads two
columns, and is followed immediately by `set_tenant`.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.cases.domain import LifecycleStatus
from app.shared.db import get_sessionmaker
from app.shared.tenant import clear_tenant, set_tenant

_log = structlog.get_logger()

#: Case states in which no worker may do anything further. A case being deleted is not a
#: processing failure, and must not be recorded as one — see `CaseNoLongerWritable`.
TERMINAL_CASE_STATES = frozenset({LifecycleStatus.DELETION_PENDING, LifecycleStatus.DELETED})

#: Stamped on every task built through `case_task`, and read by
#: `tests/security/test_task_tenant_wiring.py`. An attribute rather than a registry
#: because a registry is a list someone has to remember to add to.
TENANT_SCOPED_ATTR = "__cw_tenant_scoped__"


class CaseNoLongerWritable(Exception):
    """The case cannot accept further work: deleted, or being deleted.

    Deliberately not a failure. A task that raises is a task Celery retries, and no
    number of retries will make a deleted case writable again; a run recorded as FAILED
    would open a `PROCESSING_FAILURE` issue (ADR-0016), telling the user their document
    could not be processed when what actually happened is that they deleted the case.
    """

    def __init__(self, case_id: uuid.UUID, lifecycle_status: str) -> None:
        self.case_id = case_id
        self.lifecycle_status = lifecycle_status
        super().__init__(f"case is {lifecycle_status}")


class EvidenceNoLongerPresent(Exception):
    """The evidence item is gone or deleted. Domain §14.5: a deleted evidence item
    cannot be reprocessed. Same reasoning as above — not a failure, nothing to retry."""


@dataclass(frozen=True)
class TaskContext:
    """What a task gets once its tenant is established."""

    session: Session
    case_id: uuid.UUID
    owner_user_id: str
    evidence_item_id: uuid.UUID


def resolve_evidence_owner(
    session: Session, evidence_item_id: uuid.UUID
) -> tuple[str, uuid.UUID, str]:
    """The one privileged read: who owns this evidence, and is its case still writable.

    Runs before any tenant exists — it is what *produces* the tenant — so RLS cannot
    police it. That used to mean it worked only because every environment connects as a
    superuser, and would have returned zero rows under the non-superuser role ADR-0006 R1
    targets: every document stuck at `UPLOADED`, with the logs reporting the evidence
    absent. The privilege is now explicit instead: `evidence_owner` is a `SECURITY
    DEFINER` function (migration 0017) granted to the application role alone.

    One id in, three columns out. It is an ownership oracle by construction, because that
    is precisely what a task needs before it can know whose data it is touching — so it
    is kept as small as an oracle can be, and it is the *only* one.
    """
    row = session.execute(
        text("SELECT owner_user_id, case_id, lifecycle_status FROM evidence_owner(:id)"),
        {"id": evidence_item_id},
    ).first()
    if row is None:
        raise EvidenceNoLongerPresent(str(evidence_item_id))
    owner, case_id, lifecycle = row
    return str(owner), case_id, str(lifecycle)


@contextmanager
def case_task(
    evidence_item_id: uuid.UUID,
    *,
    sessions: sessionmaker[Session] | None = None,
) -> Iterator[TaskContext]:
    """Open a session, establish the tenant from the database, and yield it.

    Everything after `set_tenant` runs inside the tenant context, across as many commits
    as the task needs, because the `after_begin` listener re-applies on each one.

    `sessions` is injectable for one reason, and it is not tidiness: with the factory
    hard-coded, this function could only ever be driven on the superuser connection every
    environment actually uses, where RLS is inert. The security suite has a non-superuser
    login role precisely so a forgotten tenant fails closed — and a wrapper that cannot be
    pointed at it is a wrapper whose tenant nobody can test. Production passes nothing.
    """
    factory = sessions or get_sessionmaker()
    with factory() as session:
        owner, case_id, lifecycle = resolve_evidence_owner(session, evidence_item_id)
        if lifecycle in {state.value for state in TERMINAL_CASE_STATES}:
            raise CaseNoLongerWritable(case_id, lifecycle)

        set_tenant(session, owner)
        try:
            yield TaskContext(
                session=session,
                case_id=case_id,
                owner_user_id=owner,
                evidence_item_id=evidence_item_id,
            )
        finally:
            # Roll back first. `clear_tenant` issues SQL, so on a session left needing
            # rollback — any DB error, including the one that classifies a retry — it
            # raises `PendingRollbackError` *from the finally*, replacing the in-flight
            # exception. `TransientProcessingError` would then never reach the handler
            # that retries it, and the run would stay RUNNING with no retry and no
            # abandonment: the stranded document again, arriving by a different door.
            try:
                session.rollback()
                clear_tenant(session)
            except Exception:
                _log.warning("worker.tenant_clear_failed", case_id=str(case_id))


def tenant_scoped[T](func: T) -> T:
    """Mark a task as establishing its own tenant context.

    Read by the security harness. Applied by hand rather than inferred, because
    inferring it from "does the body mention case_task" is a guess, and the thing being
    guessed at is the tenant boundary.
    """
    setattr(func, TENANT_SCOPED_ATTR, True)
    return func


def log_task_outcome(task: str, **fields: Any) -> None:
    """One structured line per task, with identifiers only.

    No filename, no storage key, no document content — Domain §38.1 and threat model
    §6.4 apply to worker logs exactly as they do to request logs.
    """
    _log.info(f"task.{task}", **fields)
