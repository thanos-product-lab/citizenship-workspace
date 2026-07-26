"""Persistence access for route profiles, exposed as domain intent."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.applicants.domain import RouteProfile, RouteProfileVersion


class RouteProfileRepository:
    @staticmethod
    def get_for_case(session: Session, case_id: uuid.UUID) -> RouteProfile | None:
        return session.scalar(select(RouteProfile).where(RouteProfile.case_id == case_id))

    @staticmethod
    def get_version(session: Session, version_id: uuid.UUID) -> RouteProfileVersion | None:
        return session.get(RouteProfileVersion, version_id)

    @staticmethod
    def add_profile(session: Session, profile: RouteProfile) -> None:
        session.add(profile)

    @staticmethod
    def add_version(session: Session, version: RouteProfileVersion) -> None:
        session.add(version)
