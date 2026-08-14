"""Request/response boundary schemas for the cases API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.cases.domain import ApplicationCase, CasePhase


class CreateCaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class CaseResponse(BaseModel):
    id: uuid.UUID
    title: str
    route_key: str
    lifecycle_status: str
    support_status: str
    current_phase: str
    created_at: datetime
    updated_at: datetime
    revision: int

    @classmethod
    def from_domain(cls, case: ApplicationCase, *, phase: CasePhase) -> "CaseResponse":
        """`phase` is **required and passed in**, never read from `case.current_phase`.
        The column is written once at creation and never advanced, so reading it would
        report SETTING_UP on a fully assessed case (Domain §7.5, ADR-0009). Keeping the
        argument mandatory means a new call site has to derive it rather than inheriting
        the bug by omission."""
        return cls(
            id=case.id,
            title=case.title,
            route_key=case.route_key,
            lifecycle_status=case.lifecycle_status.value,
            support_status=case.support_status.value,
            current_phase=phase.value,
            created_at=case.created_at,
            updated_at=case.updated_at,
            revision=case.revision,
        )
