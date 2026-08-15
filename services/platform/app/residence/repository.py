"""Persistence access for residence inputs, exposed as domain intent."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.residence.domain import (
    ProposedApplicationDate,
    ProposedApplicationDateVersion,
    TravelLifecycleStatus,
    TravelRecord,
    TravelRecordVersion,
)


class ProposedApplicationDateRepository:
    @staticmethod
    def get_current_for_case(
        session: Session, case_id: uuid.UUID
    ) -> ProposedApplicationDate | None:
        """The case's current proposed-date root (M3A has at most one per case)."""
        return session.scalar(
            select(ProposedApplicationDate).where(
                ProposedApplicationDate.case_id == case_id,
                ProposedApplicationDate.is_current.is_(True),
            )
        )

    @staticmethod
    def is_current_version(session: Session, version_id: uuid.UUID) -> bool:
        """Whether this exact version is still the case's current proposed date. See the
        note on `TravelRecordRepository.is_current_version`."""
        return bool(
            session.scalar(
                select(ProposedApplicationDate.id).where(
                    ProposedApplicationDate.current_version_id == version_id
                )
            )
        )

    @staticmethod
    def get_version(
        session: Session, version_id: uuid.UUID
    ) -> ProposedApplicationDateVersion | None:
        return session.get(ProposedApplicationDateVersion, version_id)

    @staticmethod
    def add_root(session: Session, root: ProposedApplicationDate) -> None:
        session.add(root)

    @staticmethod
    def add_version(session: Session, version: ProposedApplicationDateVersion) -> None:
        session.add(version)


class TravelRecordRepository:
    @staticmethod
    def get(session: Session, travel_record_id: uuid.UUID) -> TravelRecord | None:
        return session.get(TravelRecord, travel_record_id)

    @staticmethod
    def is_current_version(session: Session, version_id: uuid.UUID) -> bool:
        """Whether this exact version is still its record's current one.

        An assessment links the version it actually read. Once the record is edited a new
        version becomes current and this returns False — which is what lets the detail
        screen say *which* input moved under a stale result, rather than only that
        something did."""
        return bool(
            session.scalar(
                select(TravelRecord.id).where(TravelRecord.current_version_id == version_id)
            )
        )

    @staticmethod
    def get_version(session: Session, version_id: uuid.UUID) -> TravelRecordVersion | None:
        return session.get(TravelRecordVersion, version_id)

    @staticmethod
    def list_active_with_current_version(
        session: Session, case_id: uuid.UUID
    ) -> list[tuple[TravelRecord, TravelRecordVersion]]:
        """Active (non-tombstoned) records with their current version, in departure
        order — the accessible chronological table (MVP §8.4). Tombstones are excluded."""
        stmt = (
            select(TravelRecord, TravelRecordVersion)
            .join(
                TravelRecordVersion,
                TravelRecord.current_version_id == TravelRecordVersion.id,
            )
            .where(
                TravelRecord.case_id == case_id,
                TravelRecord._lifecycle_status == TravelLifecycleStatus.ACTIVE.value,
            )
            .order_by(TravelRecordVersion.departure_date)
        )
        return [(record, version) for record, version in session.execute(stmt)]

    @staticmethod
    def add_record(session: Session, record: TravelRecord) -> None:
        session.add(record)

    @staticmethod
    def add_version(session: Session, version: TravelRecordVersion) -> None:
        session.add(version)
