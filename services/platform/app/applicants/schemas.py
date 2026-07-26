"""Boundary schemas for route-profile onboarding.

`RouteProfileDraftInput` is the whole answer set, every field optional — a draft is
a partially-filled form and the client PUTs the current state of all answers. Only
capture-time sanity checks live here (a date of birth cannot be in the future);
completeness and support rules are enforced at CONFIRM (a later slice), not here.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.applicants.domain import RouteProfile, RouteProfileVersion, StatusType


class RouteProfileDraftInput(BaseModel):
    date_of_birth: date | None = None
    status_type: StatusType | None = None
    status_granted_on: date | None = None
    married_to_british_citizen: bool | None = None
    may_already_be_british: bool | None = None
    # Optional optimistic-concurrency token; required once a draft exists (see service).
    expected_revision: int | None = None

    @field_validator("date_of_birth", "status_granted_on")
    @classmethod
    def _not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("date cannot be in the future")
        return value


class RouteProfileResponse(BaseModel):
    case_id: uuid.UUID
    version_number: int
    review_state: str
    date_of_birth: date | None
    status_type: str | None
    status_granted_on: date | None
    married_to_british_citizen: bool | None
    may_already_be_british: bool | None
    created_at: datetime
    revision: int

    @classmethod
    def from_domain(
        cls, profile: RouteProfile, version: RouteProfileVersion
    ) -> "RouteProfileResponse":
        return cls(
            case_id=profile.case_id,
            version_number=version.version_number,
            review_state=version.review_state,
            date_of_birth=version.date_of_birth,
            status_type=version.status_type,
            status_granted_on=version.status_granted_on,
            married_to_british_citizen=version.married_to_british_citizen,
            may_already_be_british=version.may_already_be_british,
            created_at=profile.created_at,
            revision=profile.revision,
        )
