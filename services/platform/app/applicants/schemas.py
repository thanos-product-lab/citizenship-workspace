"""Boundary schemas for route-profile onboarding.

`RouteProfileDraftInput` is the whole answer set, every field optional — a draft is
a partially-filled form and the client PUTs the current state of all answers. Only
capture-time sanity checks live here (a date of birth cannot be in the future);
completeness and support rules are enforced at CONFIRM (a later slice), not here.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.applicants.domain import RouteProfile, RouteProfileVersion, StatusType
from app.shared.dates import MAX_ENTERED_DATE, MIN_ENTERED_DATE


class RouteProfileDraftInput(BaseModel):
    # `ge`/`le` as well as the not-in-future check below, because "not in the future" was
    # the *only* bound and it admits every date back to year one. A profile carrying
    # `date_of_birth = 0995-12-11` was assessed without hesitation — `route.adult_applicant`
    # concluded SUPPORTED for an applicant 1031 years old — and `status_granted_on =
    # 0024-09-11` gave a holding period of two millennia. Every rule was correct; the
    # answer was worthless. See `app/shared/dates.py`.
    date_of_birth: date | None = Field(default=None, ge=MIN_ENTERED_DATE, le=MAX_ENTERED_DATE)
    status_type: StatusType | None = None
    status_granted_on: date | None = Field(default=None, ge=MIN_ENTERED_DATE, le=MAX_ENTERED_DATE)
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


class ConfirmRequest(BaseModel):
    # Optimistic-concurrency token: the profile revision the client last saw.
    expected_revision: int | None = None


class RequirementOutcomeResponse(BaseModel):
    requirement_key: str
    conclusion: str
    summary_code: str | None


class RouteSupportResponse(BaseModel):
    """The route-support decision. Carries the composite outcome and each upstream
    requirement outcome so the UI can explain *why* — provenance, not just a verdict."""

    support_status: str
    lifecycle_status: str
    conclusion: str
    summary_code: str | None
    confirmed_version_number: int
    rule_set: str
    semantic_version: str
    requirements: list[RequirementOutcomeResponse]


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
