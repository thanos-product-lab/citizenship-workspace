"""Evidence queries, named for domain intent rather than for CRUD.

Every method is case-scoped by argument, not by trust in RLS. RLS hides other *tenants*;
it does not hide the caller's own other cases, so the case boundary is in the WHERE
clause as well (Domain §3.1 and §52).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evidence.domain import (
    EvidenceFile,
    EvidenceItem,
    EvidenceLifecycleStatus,
)


class EvidenceRepository:
    @staticmethod
    def add_item(session: Session, item: EvidenceItem) -> None:
        session.add(item)

    @staticmethod
    def add_file(session: Session, file: EvidenceFile) -> None:
        session.add(file)

    @staticmethod
    def get_active_for_case(
        session: Session, *, case_id: uuid.UUID, evidence_item_id: uuid.UUID
    ) -> EvidenceItem | None:
        """One live item, or None for absent / another case's / deleted.

        The caller turns None into `EvidenceNotFound`, so those four cases are one
        response. A `DELETION_PENDING` item is excluded here: Domain §51.1 step 1 is
        "block further access", and that block starts at the request that asked for
        deletion, not at the purge that follows it.
        """
        stmt = select(EvidenceItem).where(
            EvidenceItem.id == evidence_item_id,
            EvidenceItem.case_id == case_id,
            EvidenceItem._lifecycle_status == EvidenceLifecycleStatus.ACTIVE.value,
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_uploaded_for_case(
        session: Session, *, case_id: uuid.UUID
    ) -> list[tuple[EvidenceItem, EvidenceFile]]:
        """The case's visible evidence, newest first.

        Joined on the item's current file. Nothing is written until an upload's bytes
        are confirmed present, so every row here is a document the case really holds.
        """
        stmt = (
            select(EvidenceItem, EvidenceFile)
            .join(EvidenceFile, EvidenceFile.id == EvidenceItem.current_file_id)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceItem._lifecycle_status == EvidenceLifecycleStatus.ACTIVE.value,
                EvidenceFile.deleted_at.is_(None),
            )
            .order_by(EvidenceItem.created_at.desc())
        )
        return [(item, file) for item, file in session.execute(stmt).all()]

    @staticmethod
    def get_current_file(session: Session, *, evidence_item_id: uuid.UUID) -> EvidenceFile | None:
        stmt = (
            select(EvidenceFile)
            .where(
                EvidenceFile.evidence_item_id == evidence_item_id,
                EvidenceFile.deleted_at.is_(None),
            )
            .order_by(EvidenceFile.version_number.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_storage_key(
        session: Session, *, case_id: uuid.UUID, storage_key: str
    ) -> tuple[EvidenceItem, EvidenceFile] | None:
        """The document already recorded against this key, if any.

        Makes recording an upload idempotent: the bytes are in the store before this
        call runs, so a retried request must find what the first one wrote rather than
        collide with it. Case-scoped like every other read - the key is not the
        authority, the case is (Domain §52).
        """
        stmt = (
            select(EvidenceItem, EvidenceFile)
            .join(EvidenceFile, EvidenceFile.evidence_item_id == EvidenceItem.id)
            .where(
                EvidenceItem.case_id == case_id,
                EvidenceFile.storage_key == storage_key,
                EvidenceFile.deleted_at.is_(None),
            )
        )
        row = session.execute(stmt).first()
        return (row[0], row[1]) if row is not None else None

    @staticmethod
    def next_version_number(session: Session, *, evidence_item_id: uuid.UUID) -> int:
        stmt = select(EvidenceFile.version_number).where(
            EvidenceFile.evidence_item_id == evidence_item_id
        )
        existing = list(session.execute(stmt).scalars().all())
        return max(existing, default=0) + 1
