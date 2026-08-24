"""The outbox reader's guarantees, and the guard that keeps its decisions complete.

The behavioural tests use a fake dispatch rather than a broker: what matters here is
which rows are claimed, in what order, and what happens to `published_at` when dispatch
succeeds or fails. Whether Celery can reach Redis is a different question and not this
file's.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.shared import outbox
from app.shared.messaging import DomainEvent
from app.shared.records import OutboxEventRecord

pytestmark = pytest.mark.integration


def _row(session: Session, event_type: str, *, created_at: datetime | None = None) -> uuid.UUID:
    record = OutboxEventRecord(
        aggregate_type="EvidenceItem",
        aggregate_id=uuid.uuid4(),
        event_type=event_type,
        payload={},
        trace_id="trace-1",
    )
    if created_at is not None:
        record.created_at = created_at
    session.add(record)
    session.flush()
    return record.id


def _reload(session: Session, row_id: uuid.UUID) -> OutboxEventRecord:
    row = session.get(OutboxEventRecord, row_id)
    assert row is not None
    return row


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __call__(self, task: str, kwargs: dict[str, object]) -> None:
        self.calls.append((task, kwargs))


def test_a_handled_event_is_dispatched_and_marked_published(db_session: Session) -> None:
    row_id = _row(db_session, "EvidenceUploaded")
    dispatch = _Recorder()

    outcome = outbox.relay_batch(db_session, dispatch)

    assert outcome.dispatched == 1
    task, kwargs = dispatch.calls[0]
    assert task == "worker.evidence.validate"
    assert kwargs["outbox_event_id"] == str(row_id)
    assert _reload(db_session, row_id).published_at is not None


def test_a_task_argument_carries_identifiers_and_nothing_else(db_session: Session) -> None:
    """Task arguments travel through Redis, which is unauthenticated in local compose.
    Nothing in them may be a credential, and nothing may be the tenant — the tenant is
    resolved from the database inside the task (`worker/context.py`)."""
    _row(db_session, "EvidenceUploaded")
    dispatch = _Recorder()

    outbox.relay_batch(db_session, dispatch)

    _, kwargs = dispatch.calls[0]
    assert set(kwargs) == {"outbox_event_id", "aggregate_id", "trace_id"}
    assert "user" not in str(kwargs).lower()
    assert "storage" not in str(kwargs).lower()


def test_an_event_with_no_consumer_is_declined_rather_than_retried_forever(
    db_session: Session,
) -> None:
    row_id = _row(db_session, "TravelRecordCreated")
    dispatch = _Recorder()

    outcome = outbox.relay_batch(db_session, dispatch)

    assert outcome.declined == 1
    assert dispatch.calls == []
    # Marked published: leaving it would hand every future pass work it must decline,
    # and bury a genuinely undelivered row in the noise.
    assert _reload(db_session, row_id).published_at is not None


def test_a_failed_dispatch_leaves_the_row_for_redelivery(db_session: Session) -> None:
    """`published_at` is set *after* the broker accepts. If it did not have to be, a
    crash between the two would lose the job silently — the exact failure the outbox
    exists to prevent."""
    row_id = _row(db_session, "EvidenceUploaded")

    def explode(task: str, kwargs: dict[str, object]) -> None:
        raise ConnectionError("broker unreachable")

    outcome = outbox.relay_batch(db_session, explode)

    assert outcome.failed == 1
    row = _reload(db_session, row_id)
    assert row.published_at is None
    assert row.attempt_count == 1
    # The failure *class*, never the message: a broker or driver error can carry bound
    # parameters, and this column is read by humans.
    assert row.last_error == "ConnectionError"
    assert "unreachable" not in (row.last_error or "")


def test_a_published_row_is_never_claimed_twice(db_session: Session) -> None:
    _row(db_session, "EvidenceUploaded")
    dispatch = _Recorder()

    assert outbox.relay_batch(db_session, dispatch).dispatched == 1
    assert outbox.relay_batch(db_session, dispatch).dispatched == 0
    assert len(dispatch.calls) == 1


def test_rows_are_claimed_oldest_first(db_session: Session) -> None:
    now = datetime.now(UTC)
    older = _row(db_session, "EvidenceUploaded", created_at=now - timedelta(minutes=5))
    newer = _row(db_session, "EvidenceUploaded", created_at=now)
    dispatch = _Recorder()

    outbox.relay_batch(db_session, dispatch)

    ordered = [call[1]["outbox_event_id"] for call in dispatch.calls]
    assert ordered == [str(older), str(newer)]


def test_the_batch_limit_is_respected(db_session: Session) -> None:
    for _ in range(4):
        _row(db_session, "EvidenceUploaded")
    dispatch = _Recorder()

    assert outbox.relay_batch(db_session, dispatch, limit=2).dispatched == 2


# --- the coverage guard -------------------------------------------------------------


def _all_event_types() -> set[str]:
    """Every `event_type` the application can emit, derived from the class hierarchy.

    Derived rather than listed, for the same reason `test_rls_coverage` derives its
    tables from Postgres: a hand-maintained list is a list that goes stale silently, and
    the failure mode is an event nobody decided what to do with.
    """
    import app.applicants.domain
    import app.assessments.domain
    import app.cases.domain
    import app.evidence.domain
    import app.issues.domain
    import app.residence.domain  # noqa: F401

    found: set[str] = set()
    pending = list(DomainEvent.__subclasses__())
    while pending:
        cls = pending.pop()
        pending.extend(cls.__subclasses__())
        event_type = getattr(cls, "event_type", None)
        if isinstance(event_type, str):
            found.add(event_type)
    return found


def test_every_event_type_has_a_decision_recorded() -> None:
    """A new domain event must be either handled or explicitly declined.

    Without this, adding an event means adding a row the relay declines with a warning
    nobody reads — the work silently never happens, and the symptom appears milestones
    later as "why did nothing process that".
    """
    undecided = sorted(_all_event_types() - outbox.known_event_types())
    assert undecided == [], (
        f"event types with no entry in HANDLERS or NO_CONSUMER: {undecided}. Decide what "
        "consumes each one, or record that nothing does."
    )


def test_the_check_has_event_types_to_check() -> None:
    """Guard against the derivation returning nothing — which would make the assertion
    above pass while checking an empty set. The lesson of `test_the_check_has_routes_to
    _check`, applied to a different derivation."""
    assert len(_all_event_types()) > 10


def test_no_decision_names_an_event_that_does_not_exist() -> None:
    """A stale entry is an entry nobody is reading, and in `HANDLERS` it is worse than
    stale: it is a handler wired to a message that can never arrive."""
    stale = sorted(outbox.known_event_types() - _all_event_types())
    assert stale == [], f"HANDLERS/NO_CONSUMER name event types that no longer exist: {stale}"
