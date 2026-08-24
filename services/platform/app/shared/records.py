"""Append-only infrastructure tables written by the unit of work.

Three sinks, one atomic write:

- `DomainEventRecord` — the immutable fact that something happened (§38).
- `AuditEntryRecord`  — the security/user-visible action log (§39).
- `OutboxEventRecord` — the transactional outbox for async work (§40).

These are the only rows the unit of work considers "infrastructure": a commit that
changes any *other* table without also writing a domain event is rejected. See
`app.shared.unit_of_work`.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base


class DomainEventRecord(Base):
    __tablename__ = "domain_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(255))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditEntryRecord(Base):
    __tablename__ = "audit_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(index=True)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[str] = mapped_column(String(60))
    target_id: Mapped[uuid.UUID] = mapped_column()
    trace_id: Mapped[str | None] = mapped_column(String(64))
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEventRecord(Base):
    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[uuid.UUID] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Carried forward so a trace spans the browser, the API and the worker — the hop
    # M7 introduces, and the one the chain used to break at.
    trace_id: Mapped[str | None] = mapped_column(String(64))
    # NULL published_at = not yet delivered. Set *after* the broker accepts the task, so
    # a crash between the two redelivers: at-least-once, never exactly-once.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    # Failure *class* only — never an exception string, which can carry bound parameters
    # (ADR-0016, and the retried-upload leak found in slice 1).
    last_error: Mapped[str | None] = mapped_column(String(500))
