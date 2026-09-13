"""Destroying a case (Domain §51.2).

The counterpart to `app/evidence/purge.py`, and it inherits that module's three
properties: it refuses anything that is not `DELETION_PENDING`, it destroys bytes before
it forgets the keys that address them, and it emits no domain event because
`CaseDeletionRequested` already announced what is being carried out.

What is different is scale, and scale is the whole difficulty. Evidence deletion destroys
one aggregate; this destroys every row in the case. Two design decisions follow.

**The table order is explicit and the coverage check is derived.** `_DELETION_ORDER` below
is a hand-written list, children before parents, because a reviewer has to be able to read
what this destroys — a clever traversal that produced the right answer would be a thing
nobody could audit. But a hand-written list is exactly how a table added in a later
milestone gets silently missed, so it is not *trusted*: `test_every_case_scoped_table_is_
purged` derives the case-scoped set from the live schema, the same way
`test_rls_coverage.py` derives it for policies, and fails on the migration that introduces
a table this list does not name. Explicit for reading, derived for correctness.

**Events are found by aggregate, not by case.** `domain_events` and `outbox_events` key on
`aggregate_id`, which for a case-level event is the case id and for everything else is the
id of a travel record, an evidence item, a claim. So the ids have to be collected *before*
the rows holding them are deleted. They are in scope at all because `domain_events.actor_id`
is the user's own identifier — the payloads are ids and enums, which is CLAUDE.md §11 being
honoured, but the actor column is not covered by that and is directly identifying.

**What survives, and why it is not a contradiction.** The `cases` row itself, scrubbed:
Domain §7.4 says a `DELETED` case retains "a minimal non-identifying deletion audit", and
this row is it. `title` is cleared because a user's name for their case is very often a
person's name, and `owner_user_id` is cleared because a deletion audit that names the
person is not a non-identifying one. What remains — the id, the route key, when deletion
was asked for and when it completed — records that a deletion happened without recording
whose.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult, text
from sqlalchemy.orm import Session

from app.cases.domain import ApplicationCase, LifecycleStatus
from app.core.storage import StorageAdapter, StorageError

_log = structlog.get_logger()


def _via(column: str, parent: str, parent_predicate: str = "case_id = :case_id") -> str:
    """A predicate for a table that has no `case_id` of its own: scope it through its
    parent. Nests, which is how `evidence_file_texts` reaches a case two joins away."""
    return f"{column} IN (SELECT id FROM {parent} WHERE {parent_predicate})"


_OWN = "case_id = :case_id"
_EVIDENCE = _via("evidence_item_id", "evidence_items")

#: Every case-scoped table, children before parents, as `(table, predicate)`.
#:
#: Fifteen tables carry a `case_id` and say so directly; the other nine are reachable only
#: through a parent and name the join that reaches them. Both forms are written out rather
#: than traversed, so the blast radius of this module is legible in one screen.
#:
#: `cases` is deliberately absent — it becomes the tombstone, not a casualty.
_DELETION_ORDER: tuple[tuple[str, str], ...] = (
    ("assessment_input_links", _via("assessment_result_id", "assessment_results")),
    ("assessment_results", _OWN),
    ("assessment_runs", _OWN),
    ("evidence_file_texts", _via("evidence_file_id", "evidence_files", _EVIDENCE)),
    ("fact_evidence_links", _OWN),
    ("fact_versions", _via("case_fact_id", "case_facts")),
    ("claim_review_decisions", _OWN),
    ("case_facts", _OWN),
    ("extracted_claims", _OWN),
    ("extraction_runs", _OWN),
    ("evidence_processing_runs", _EVIDENCE),
    ("evidence_travel_links", _OWN),
    ("evidence_files", _EVIDENCE),
    ("evidence_items", _OWN),
    ("issue_resolutions", _via("issue_id", "issues")),
    ("issues", _OWN),
    ("travel_record_versions", _via("travel_record_id", "travel_records")),
    ("travel_records", _OWN),
    (
        "proposed_application_date_versions",
        _via("proposed_application_date_id", "proposed_application_dates"),
    ),
    ("proposed_application_dates", _OWN),
    ("route_profile_versions", _via("route_profile_id", "route_profiles")),
    ("route_profiles", _OWN),
    ("audit_entries", _OWN),
    ("case_memberships", _OWN),
)

#: Tables whose primary keys can appear as a `domain_events.aggregate_id`. Collected before
#: the deletes above run, because afterwards there is nothing left to collect them from.
_AGGREGATE_SOURCES: tuple[tuple[str, str], ...] = tuple(
    (table, predicate)
    for table, predicate in _DELETION_ORDER
    if table not in {"assessment_input_links", "audit_entries"}
)


@dataclass
class CasePurgeOutcome:
    case_id: uuid.UUID
    #: False when there was nothing left to do — an already-purged case under redelivery.
    purged: bool
    reason: str
    objects_deleted: int = 0
    rows_deleted: int = 0
    events_deleted: int = 0
    model_runs_scrubbed: int = 0
    #: Per-table counts, for the log line and for tests that need to see the shape.
    by_table: dict[str, int] = field(default_factory=dict)


def _execute(session: Session, statement: str, params: Mapping[str, Any]) -> int:
    """Run one DML statement and return the rows it touched.

    `Session.execute` is typed as returning `Result`, which has no `rowcount`; DML actually
    returns a `CursorResult`, which does. The cast is here once rather than at each of the
    three call sites, and the counts it produces are what the outcome and the log line
    report — a purge that says how much it destroyed is a purge whose completeness can be
    checked afterwards.
    """
    result = session.execute(text(statement), params)
    return cast("CursorResult[Any]", result).rowcount


def purge_case(
    session: Session,
    storage: StorageAdapter,
    *,
    case_id: uuid.UUID,
    trace_id: str | None = None,
) -> CasePurgeOutcome:
    """Carry out §51.2 steps 4 through 8.

    Steps 1-3 are `request_deletion`'s: the case is already `DELETION_PENDING`, writes are
    already blocked, and no new work can be scheduled against it.

    Raises `StorageError` when the store cannot be reached, so the task retries and the
    case stays `DELETION_PENDING`. That is the honest intermediate state — unreachable to
    its owner, with its content not yet destroyed — and it is the reason `mark_deleted`
    happens last: a case must never claim to be `DELETED` while its bytes are in a bucket.
    """
    case = session.get(ApplicationCase, case_id)
    if case is None:
        return CasePurgeOutcome(case_id, purged=False, reason="absent")

    if case.lifecycle_status is LifecycleStatus.DELETED:
        # Redelivery. The relay is at-least-once and this is the expected second pass.
        return CasePurgeOutcome(case_id, purged=False, reason="already_purged")

    if case.lifecycle_status is not LifecycleStatus.DELETION_PENDING:
        # Nobody asked for this case to be deleted. Returning rather than raising: no
        # number of retries can make an unrequested deletion correct.
        _log.error(
            "case.purge_refused",
            case_id=str(case_id),
            lifecycle_status=case.lifecycle_status.value,
            trace_id=trace_id,
        )
        return CasePurgeOutcome(case_id, purged=False, reason="not_pending")

    bind = {"case_id": case_id}

    # §51.2 step 4. Bytes first: the storage key addresses the object, so deleting the rows
    # that hold the keys before deleting the objects would strand content with nothing
    # pointing at it. Every file version, not only the current one — a replaced document's
    # earlier bytes are as much the user's content as the latest.
    storage_keys = [
        row[0]
        for row in session.execute(
            text(
                "SELECT f.storage_key FROM evidence_files f "
                "JOIN evidence_items i ON i.id = f.evidence_item_id "
                "WHERE i.case_id = :case_id AND f.storage_key <> ''"
            ),
            bind,
        ).all()
    ]
    for key in storage_keys:
        storage.delete(key)

    # §51.2 step 6, and it has to happen *before* the deletes below: `model_runs` has no
    # `case_id` — deliberately, so provider telemetry carries no tenant (migration 0025) —
    # so `extraction_runs` is the only route to this case's runs, and it is about to go.
    #
    # `output_hash` is a fingerprint of model output about a destroyed document: retaining
    # it would let anyone with database access confirm a specific output had been produced
    # here, which is the question a deletion is meant to stop answering. The same argument
    # `evidence/purge.py` makes for `input_hash`, one table further out.
    #
    # Through a `SECURITY DEFINER` function because `app_rls` has `INSERT, SELECT` and no
    # `UPDATE` on `model_runs` — telemetry is append-only from the request path, and
    # granting the role UPDATE to serve one purge would widen every handler's privilege.
    model_runs_scrubbed = session.execute(
        text("SELECT case_scrub_model_run_hashes(:case_id)"), bind
    ).scalar_one()

    aggregate_ids = _aggregate_ids(session, case_id=case_id)

    # §51.2 step 5.
    by_table: dict[str, int] = {}
    for table, predicate in _DELETION_ORDER:
        deleted = _execute(session, f"DELETE FROM {table} WHERE {predicate}", bind)
        if deleted:
            by_table[table] = deleted

    events_deleted = _delete_events(session, aggregate_ids=aggregate_ids)

    # §51.2 steps 7 and 8, in that order and in one transaction.
    #
    # The transition goes through the aggregate, which refuses any state but
    # `DELETION_PENDING` — `lifecycle_status` is not in the RLS predicate, so a tenant-scoped
    # connection can make it. Releasing ownership cannot be: the policy on `cases` *is*
    # `owner_user_id = current_setting('app.user_id')`, as both USING and WITH CHECK, so a
    # tenant can never set that column to anything but itself. The row's ownership is what
    # the policy is made of, which makes giving it up necessarily a privileged act — hence
    # the definer function, called last, because after it the row is invisible to the tenant
    # doing the work. Both writes commit together: a `DELETED` case still naming its owner is
    # not a state this should be able to stop in.
    at = datetime.now(UTC)
    case.updated_at = at
    case.mark_deleted(at=at)
    session.flush()
    session.execute(text("SELECT case_release_ownership(:case_id)"), bind)
    session.commit()

    outcome = CasePurgeOutcome(
        case_id=case_id,
        purged=True,
        reason="purged",
        objects_deleted=len(storage_keys),
        rows_deleted=sum(by_table.values()),
        events_deleted=events_deleted,
        model_runs_scrubbed=model_runs_scrubbed,
        by_table=by_table,
    )
    # Counts and ids only — no title, no key, no filename (Domain §38.1).
    _log.info(
        "case.purged",
        case_id=str(case_id),
        objects_deleted=outcome.objects_deleted,
        rows_deleted=outcome.rows_deleted,
        events_deleted=outcome.events_deleted,
        model_runs_scrubbed=outcome.model_runs_scrubbed,
        trace_id=trace_id,
    )
    return outcome


def _aggregate_ids(session: Session, *, case_id: uuid.UUID) -> list[uuid.UUID]:
    """Every id that could appear as an event's `aggregate_id`, the case's own included."""
    ids: list[uuid.UUID] = [case_id]
    for table, predicate in _AGGREGATE_SOURCES:
        ids.extend(
            row[0]
            for row in session.execute(
                text(f"SELECT id FROM {table} WHERE {predicate}"), {"case_id": case_id}
            ).all()
        )
    return ids


def _delete_events(session: Session, *, aggregate_ids: list[uuid.UUID]) -> int:
    """Remove this case's append-only event rows.

    An append-only log being deleted deserves a sentence. `domain_events` is append-only
    *as a write discipline* — nothing updates a row, because an event is a statement about
    something that happened. Deletion is not an amendment of that statement; it is the
    record ceasing to be kept, which is what a deletion request asks for. The alternative,
    retaining events for a case whose every other row is gone, keeps `actor_id` — the
    user's identifier — against ids that now reference nothing.

    Unpublished `outbox_events` go too, which is the "cancel safe-to-cancel tasks" half of
    §51.2 step 3 that `request_deletion` could not do: a row not yet relayed is work not yet
    dispatched, and dispatching it after the purge would hand the worker a job whose subject
    no longer exists.
    """
    if not aggregate_ids:
        return 0
    total = 0
    for table in ("domain_events", "outbox_events"):
        total += _execute(
            session,
            f"DELETE FROM {table} WHERE aggregate_id = ANY(:ids)",
            {"ids": aggregate_ids},
        )
    return total


__all__ = ["_DELETION_ORDER", "CasePurgeOutcome", "StorageError", "purge_case"]
