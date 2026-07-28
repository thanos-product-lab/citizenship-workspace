"""Boundary schemas for selecting a proposed application date.

A proposed application date is a forward-looking planning intention, so there is no
future/past constraint here (a Pydantic `date` already rejects a malformed value).
Domain validity — e.g. a date earlier than the status-holding period allows — is an
M3B rules concern, deliberately not enforced at this input boundary.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.residence.domain import ProposedApplicationDate, ProposedApplicationDateVersion


class SelectApplicationDateInput(BaseModel):
    application_date: date
    # Optimistic-concurrency token: the root revision the client last saw. Omitted on
    # the first selection (no root exists yet); required to change an existing date.
    expected_revision: int | None = None


class ProposedApplicationDateResponse(BaseModel):
    case_id: uuid.UUID
    application_date: date
    version_number: int
    review_state: str
    source: str
    is_current: bool
    revision: int
    created_at: datetime

    @classmethod
    def from_domain(
        cls, root: ProposedApplicationDate, version: ProposedApplicationDateVersion
    ) -> "ProposedApplicationDateResponse":
        return cls(
            case_id=root.case_id,
            application_date=version.application_date,
            version_number=version.version_number,
            review_state=version.review_state,
            source=version.source,
            is_current=root.is_current,
            revision=root.revision,
            created_at=root.created_at,
        )
