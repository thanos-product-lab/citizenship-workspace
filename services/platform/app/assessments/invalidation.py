"""Blunt stale propagation: the transactional seam between a residence input change and the
assessment results that depend on it (Domain §41).

When a residence input changes (the proposed application date, or any travel record), every
current residence result is marked STALE **in the same transaction** as the input change —
the conclusion is untouched, only its currency, so the user sees the last conclusion clearly
flagged as needing recalculation. This is deliberately *blunt* (all residence results, not a
per-dependency subset); selective invalidation is M6 (ADR-0008).

This module imports only the assessment repository and the residence *key list* — never the
residence service — so the residence write commands can call it without an import cycle.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.assessments.domain import AssessmentInvalidated
from app.assessments.repository import AssessmentRepository
from app.shared.unit_of_work import UnitOfWork


class StaleReason:
    APPLICATION_DATE_CHANGED = "APPLICATION_DATE_CHANGED"
    TRAVEL_RECORD_CHANGED = "TRAVEL_RECORD_CHANGED"


def invalidate_residence_results(
    session: Session, uow: UnitOfWork, *, case_id: uuid.UUID, reason_code: str
) -> int:
    """Mark all current residence results STALE and, if any were, emit AssessmentInvalidated on
    the caller's unit of work (so the mark and the event commit atomically with the input
    change). A no-op before the first assessment run exists — nothing to invalidate."""
    affected = AssessmentRepository.mark_current_residence_results_stale(
        session, case_id, reason_code, datetime.now(UTC)
    )
    if affected:
        uow.emit(
            AssessmentInvalidated(
                aggregate_id=case_id,
                reason_code=reason_code,
                affected_count=len(affected),
            ),
            case_id=case_id,
            action="assessment.invalidated",
            target_type="ApplicationCase",
            target_id=case_id,
        )
    return len(affected)
