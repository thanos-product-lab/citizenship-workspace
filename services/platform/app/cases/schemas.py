"""Request/response boundary schemas for the cases API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.cases.domain import ApplicationCase


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
    def from_domain(cls, case: ApplicationCase) -> "CaseResponse":
        return cls(
            id=case.id,
            title=case.title,
            route_key=case.route_key,
            lifecycle_status=case.lifecycle_status.value,
            support_status=case.support_status.value,
            current_phase=case.current_phase,
            created_at=case.created_at,
            updated_at=case.updated_at,
            revision=case.revision,
        )
