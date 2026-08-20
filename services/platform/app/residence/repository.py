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
                    ProposedApplicationDate.current_version_id == version_id,
                    # A case may hold more than one root; only the current one counts.
                    ProposedApplicationDate.is_current.is_(True),
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
    def get_record_for_version(
        session: Session, version_id: uuid.UUID
    ) -> tuple[TravelRecord, TravelRecordVersion] | None:
        """The record and version behind a linked version id.

        Returns both because the two answer different questions and callers need both:
        the *version* holds the values a rule read, the *record* holds the lifecycle — and
        a removed record is a tombstone whose `current_version_id` still points at its last
        version, so a check that reads only the version cannot tell it apart from a live
        one."""
        version = session.get(TravelRecordVersion, version_id)
        if version is None:
            return None
        record = session.get(TravelRecord, version.travel_record_id)
        return (record, version) if record is not None else None

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
    def map_versions_to_records(session: Session, case_id: uuid.UUID) -> dict[str, str]:
        """Every travel-record version in the case, mapped to the record it belongs to —
        superseded versions included.

        A limitation names the *versions* an evaluator read. When the result carrying it is
        stale, those versions are no longer current, so a current-only lookup silently drops
        them: the overlap a rule found looks resolved and the queue under-reports it.
        """
        rows = session.execute(
            select(TravelRecordVersion.id, TravelRecordVersion.travel_record_id)
            .join(TravelRecord, TravelRecord.id == TravelRecordVersion.travel_record_id)
            .where(TravelRecord.case_id == case_id)
        ).all()
        return {str(version_id): str(record_id) for version_id, record_id in rows}

    @staticmethod
    def add_record(session: Session, record: TravelRecord) -> None:
        session.add(record)

    @staticmethod
    def add_version(session: Session, version: TravelRecordVersion) -> None:
        session.add(version)
