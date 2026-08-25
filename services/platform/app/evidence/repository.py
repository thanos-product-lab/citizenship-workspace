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
    EvidenceFileText,
    EvidenceItem,
    EvidenceLifecycleStatus,
    EvidenceProcessingRun,
    EvidenceTravelLink,
    LinkAvailability,
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
    def latest_runs_for_case(
        session: Session, *, case_id: uuid.UUID
    ) -> dict[uuid.UUID, EvidenceProcessingRun]:
        """The most recent processing run per evidence item.

        Fetched for the whole library in one query rather than per row: the library is
        the only reader, and a per-item lookup here is the N+1 that turns a page into a
        hundred round trips the first time someone uploads a hundred documents.
        """
        stmt = (
            select(EvidenceProcessingRun)
            .join(EvidenceItem, EvidenceItem.id == EvidenceProcessingRun.evidence_item_id)
            .where(EvidenceItem.case_id == case_id)
            .order_by(
                EvidenceProcessingRun.evidence_item_id,
                EvidenceProcessingRun.started_at.desc(),
            )
        )
        latest: dict[uuid.UUID, EvidenceProcessingRun] = {}
        for run in session.execute(stmt).scalars().all():
            latest.setdefault(run.evidence_item_id, run)
        return latest

    @staticmethod
    def texts_for_case(
        session: Session, *, case_id: uuid.UUID
    ) -> dict[uuid.UUID, EvidenceFileText]:
        """Extraction results per file, for the whole library in one query.

        `content` is a deferred column, so this loads the counts and flags without
        pulling every document's text into the API process — which is the reason the
        text lives in its own table at all.
        """
        stmt = (
            select(EvidenceFileText)
            .join(EvidenceFile, EvidenceFile.id == EvidenceFileText.evidence_file_id)
            .join(EvidenceItem, EvidenceItem.id == EvidenceFile.evidence_item_id)
            .where(EvidenceItem.case_id == case_id)
        )
        return {text.evidence_file_id: text for text in session.execute(stmt).scalars().all()}

    @staticmethod
    def text_for_file(session: Session, *, evidence_file_id: uuid.UUID) -> EvidenceFileText | None:
        return session.execute(
            select(EvidenceFileText).where(EvidenceFileText.evidence_file_id == evidence_file_id)
        ).scalar_one_or_none()

    @staticmethod
    def latest_run(
        session: Session, *, evidence_item_id: uuid.UUID
    ) -> EvidenceProcessingRun | None:
        stmt = (
            select(EvidenceProcessingRun)
            .where(EvidenceProcessingRun.evidence_item_id == evidence_item_id)
            .order_by(EvidenceProcessingRun.started_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalars().first()

    @staticmethod
    def next_version_number(session: Session, *, evidence_item_id: uuid.UUID) -> int:
        stmt = select(EvidenceFile.version_number).where(
            EvidenceFile.evidence_item_id == evidence_item_id
        )
        existing = list(session.execute(stmt).scalars().all())
        return max(existing, default=0) + 1


class EvidenceLinkRepository:
    """Queries over `evidence_travel_links` (Domain §11.9).

    Its own class rather than more methods on `EvidenceRepository`: a link is a relation
    between two aggregates, and every question asked of it is about coverage rather than
    about a document. Keeping them apart stops "list the case's evidence" and "list what
    evidences this case's trips" from becoming the same method with a flag.
    """

    @staticmethod
    def add(session: Session, link: EvidenceTravelLink) -> None:
        session.add(link)

    @staticmethod
    def live_for_case(session: Session, *, case_id: uuid.UUID) -> list[EvidenceTravelLink]:
        """Every link currently counting as coverage, ordered for determinism.

        Ordered by id because the rule that reads this writes one `AssessmentInputLink`
        per row, and an unordered read would make provenance rows arrive in a different
        order on every recalculation — comparing two assessments would then show a diff
        where nothing changed.
        """
        stmt = (
            select(EvidenceTravelLink)
            .where(
                EvidenceTravelLink.case_id == case_id,
                EvidenceTravelLink._availability == LinkAvailability.AVAILABLE.value,
            )
            .order_by(EvidenceTravelLink.id)
        )
        return list(session.execute(stmt).scalars())

    @staticmethod
    def live_between(
        session: Session,
        *,
        case_id: uuid.UUID,
        travel_record_id: uuid.UUID,
        evidence_item_id: uuid.UUID,
    ) -> EvidenceTravelLink | None:
        """The live link joining these two, if there is one.

        Read before attaching so a repeated attach is answered as "already attached"
        rather than by a unique-index violation surfacing as a 500. The index is still
        there — this is the courteous path, not the guarantee.
        """
        stmt = select(EvidenceTravelLink).where(
            EvidenceTravelLink.case_id == case_id,
            EvidenceTravelLink.travel_record_id == travel_record_id,
            EvidenceTravelLink.evidence_item_id == evidence_item_id,
            EvidenceTravelLink._availability == LinkAvailability.AVAILABLE.value,
        )
        return session.execute(stmt).scalar_one_or_none()

    @staticmethod
    def live_for_evidence_item(
        session: Session, *, case_id: uuid.UUID, evidence_item_id: uuid.UUID
    ) -> list[EvidenceTravelLink]:
        """Every live link pointing at one document — what slice 5 withdraws on deletion."""
        stmt = (
            select(EvidenceTravelLink)
            .where(
                EvidenceTravelLink.case_id == case_id,
                EvidenceTravelLink.evidence_item_id == evidence_item_id,
                EvidenceTravelLink._availability == LinkAvailability.AVAILABLE.value,
            )
            .order_by(EvidenceTravelLink.id)
        )
        return list(session.execute(stmt).scalars())
