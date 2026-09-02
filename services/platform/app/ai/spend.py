"""The daily spend ceiling: a hard stop, not a warning.

Moved forward from M11 because the first live model call is when runaway cost
becomes possible (IMPLEMENTATION_ROADMAP §1, change 8).

**Why a hard stop and not a log line.** A budget that only warns is not a budget.
But the more interesting half is what happens to the *user*: a refused call must
produce a visible, terminal state with a reason they can act on, never a silent
skip. A document that quietly stops processing while the UI keeps saying "analysing"
is false reassurance, which directive 7 ranks above almost everything else. That is
why `SpendCeilingReached` is an exception the pipeline turns into a state, rather
than a boolean the caller may ignore.

**What the lock does, precisely, and what it does not.** Cost is not knowable before
the call, so the ledger is touched twice: `reserve` locks the day's row and refuses
if the total already meets the ceiling; `record` locks it again and adds what was
actually spent. The lock exists to stop the lost update — two workers reading the
same total and each writing it back as though the other had not spent, which loses
one of the two costs entirely and would make the ledger drift *downwards* under
exactly the concurrency a runaway produces.

It does **not** serialise the calls themselves, and so it does not stop N workers
all passing a check taken just under the ceiling. The overshoot is bounded by
`concurrency x cost-per-call`; at the ~$0.00026 per document the M8 spike measured
and a handful of worker slots, that is fractions of a penny. Holding the lock across
the provider call would close the gap and would serialise every model call in the
deployment behind one row — a worse property than a bounded overshoot. The bound is
stated here rather than implied, because "we have a spend ceiling" and "we cannot
exceed the ceiling by a cent" are different claims and only the first is true.
"""

from datetime import date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ai.domain import AiDailySpend

_log = structlog.get_logger()


class SpendCeilingReached(Exception):
    """The day's ceiling is spent. Terminal for this invocation.

    Carries the numbers so the state a user is shown can say *what* stopped and
    when it clears, rather than "processing failed".
    """

    def __init__(self, *, spent_usd: float, ceiling_usd: float, day: date) -> None:
        self.spent_usd = spent_usd
        self.ceiling_usd = ceiling_usd
        self.day = day
        super().__init__(
            f"AI spend ceiling reached for {day.isoformat()} (UTC): "
            f"${spent_usd:.4f} of ${ceiling_usd:.2f}. Resets at 00:00 UTC."
        )


def _lock_day(session: Session, day: date) -> AiDailySpend:
    """Fetch the day's row for update, creating it if this is the day's first call.

    `ON CONFLICT DO NOTHING` then re-select, rather than "select, and insert if
    missing": two workers on the first call of the day would both find nothing and
    both insert, and one would take an IntegrityError on a path whose whole job is
    to be reliable. The insert is unconditional and idempotent; the lock is taken
    afterwards, on a row that is then guaranteed to exist.
    """
    session.execute(
        insert(AiDailySpend).values(day=day).on_conflict_do_nothing(index_elements=["day"])
    )
    row = session.execute(
        select(AiDailySpend).where(AiDailySpend.day == day).with_for_update()
    ).scalar_one()
    return row


def utc_day(at: datetime) -> date:
    """The ledger's day. UTC always — a ceiling that resets at local midnight resets
    at a different instant depending on what the process thinks its timezone is, and
    the symptom is a doubled budget on the day the clocks change."""
    return at.date()


def reserve(session: Session, *, at: datetime, ceiling_usd: float) -> None:
    """Refuse the call if the day's ceiling is already met. Raises, never returns False.

    Raising rather than returning a boolean is deliberate: a caller can forget to
    check a return value, and the failure mode of forgetting *this* one is an
    unbounded bill.
    """
    day = utc_day(at)
    row = _lock_day(session, day)
    spent = float(row.spent_usd or 0)
    if spent >= ceiling_usd:
        _log.warning(
            "ai.spend_ceiling_reached",
            day=day.isoformat(),
            spent_usd=spent,
            ceiling_usd=ceiling_usd,
        )
        raise SpendCeilingReached(spent_usd=spent, ceiling_usd=ceiling_usd, day=day)


def record(session: Session, *, at: datetime, cost_usd: float) -> float:
    """Add what a call actually cost, and return the day's new total.

    Called for every invocation including the failed ones: a provider bills for the
    tokens it processed whether or not the output validated, and a ledger that only
    counted successes would under-report exactly the runaway — a loop of
    schema-invalid retries — that the ceiling exists to stop.
    """
    day = utc_day(at)
    row = _lock_day(session, day)
    row.spent_usd = (row.spent_usd or Decimal(0)) + Decimal(str(cost_usd))
    row.calls = (row.calls or 0) + 1
    return float(row.spent_usd)


def spent_today(session: Session, *, at: datetime) -> float:
    """The day's total, without locking. For reporting only — never for a decision,
    because a value read without the lock is stale the moment it is returned."""
    row = session.get(AiDailySpend, utc_day(at))
    return float(row.spent_usd or 0) if row else 0.0
