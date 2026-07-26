"""The single transactional unit of work.

Constraint from the M2 plan: *every* state-mutating command commits state, domain
event, audit entry, and outbox row **together, or not at all**. This class is the
only sanctioned commit path for a mutation. Its guarantee:

    A commit that changes any non-infrastructure table without emitting at least
    one domain event raises `StateWithoutEventError`.

So "state written but no outbox row" is structurally impossible, not merely
discouraged. `emit()` writes the event, its outbox twin, and the audit entry in one
call, so the three can never drift apart.

Optimistic concurrency (SQLAlchemy `version_id_col`) surfaces here too: a stale
`revision` raises `StaleDataError` on flush, which we translate to the domain-level
`ConcurrencyConflict` (→ HTTP 409), never a silent overwrite.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.shared.errors import ConcurrencyConflict, StateWithoutEventError
from app.shared.messaging import DomainEvent
from app.shared.records import AuditEntryRecord, DomainEventRecord, OutboxEventRecord
from app.shared.trace import current_trace_id

# Rows the unit of work treats as infrastructure. A commit touching anything else
# without an emitted event is the failure the guard catches.
_INFRA_TYPES = (DomainEventRecord, AuditEntryRecord, OutboxEventRecord)


class UnitOfWork:
    def __init__(self, session: Session, *, actor_id: str, actor_type: str = "USER") -> None:
        self.session = session
        self._actor_id = actor_id
        self._actor_type = actor_type
        self._events = 0

    def emit(
        self,
        event: DomainEvent,
        *,
        case_id: uuid.UUID,
        action: str,
        target_type: str,
        target_id: uuid.UUID,
        safe_metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a domain event, its outbox twin, and the audit entry atomically."""
        trace = current_trace_id()
        payload = event.payload()
        self.session.add(
            DomainEventRecord(
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                actor_id=self._actor_id,
                trace_id=trace,
                payload=payload,
            )
        )
        self.session.add(
            OutboxEventRecord(
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                event_type=event.event_type,
                payload=payload,
            )
        )
        self.session.add(
            AuditEntryRecord(
                case_id=case_id,
                actor_type=self._actor_type,
                actor_id=self._actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                trace_id=trace,
                safe_metadata=safe_metadata or {},
            )
        )
        self._events += 1

    def commit(self) -> None:
        # Inspect the pending changes *before* flushing: a flush empties
        # `session.new`, which would hide exactly the state change we guard against.
        # autoflush is disabled on the sessionmaker, so nothing has flushed yet.
        if self._events == 0 and self._has_business_state_change():
            self.session.rollback()
            raise StateWithoutEventError(
                "business state changed without an emitted domain event"
            )
        try:
            self.session.commit()  # flushes first; a stale revision raises here
        except StaleDataError as exc:
            self.session.rollback()
            raise ConcurrencyConflict() from exc

    def _has_business_state_change(self) -> bool:
        changed = [*self.session.new, *self.session.dirty, *self.session.deleted]
        return any(not isinstance(obj, _INFRA_TYPES) for obj in changed)
