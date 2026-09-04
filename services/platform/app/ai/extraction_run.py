"""One AI capability invocation against one immutable evidence file version.

`EVIDENCE_AND_CLAIM_LIFECYCLE_RFC.md` §8, with the eleven provider/cost/latency
columns replaced by a reference to `model_runs` — see **ADR-0025** for why copying
them would make two tables disagree the first time a call retried.

This is the case-scoped half of the pair. `ModelRun` is deployment-wide telemetry
about a provider call; `ExtractionRun` is the domain record that *this case's* file was
read by *this capability*, and it carries `case_id`, an RLS policy, and a place in the
case-deletion path. The join between them is one hop and answers "what did reading this
document cost" without either table holding the other's concerns.

**It is not a claim, and slice 2 creates none.** The classifier's category lives here,
on the run, because a category is routing metadata: no requirement reads it, no
assessment depends on it, and there is nothing in the fact model it could be confirmed
into. `ExtractedClaim` arrives in slice 3a for values that *can* become facts, and
keeping the two apart is what lets this slice ship without shipping something that
half-resembles the claim path.

**Immutable once settled.** A run reaches a terminal status and keeps it. Reprocessing
creates a *new* run (RFC §17: "Previous runs and claims remain unchanged"), which is
what makes "what did we think this document was, before?" a question with an answer.
"""

import hashlib
import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.domain import utcnow
from app.shared.db import Base


class ExtractionRunStatus(StrEnum):
    """How the capability's invocation ended, in the domain's vocabulary rather than
    the provider's.

    Distinct from `ModelRunStatus`, which records what the *provider* did. A run can be
    `REFUSED_NO_BUDGET` with no `ModelRun` at all, and a run can have a `ModelRun` that
    `SUCCEEDED` while this says `FAILED` because the output was unusable. Collapsing
    them would mean a domain reader had to understand provider failure modes to know
    whether a document was processed.
    """

    SUCCEEDED = "SUCCEEDED"
    #: The capability ran and declined to choose — `UNSUPPORTED` or `AMBIGUOUS`. A
    #: success in every sense that matters (AI_EVALUATION_PLAN §3.2), recorded
    #: separately so abstention can be measured rather than inferred.
    ABSTAINED = "ABSTAINED"
    #: The provider was reached and nothing usable came back.
    FAILED = "FAILED"
    #: The day's spend ceiling was already met, so nothing was attempted.
    REFUSED_NO_BUDGET = "REFUSED_NO_BUDGET"
    #: The task ran out of its AI budget before this call could start.
    REFUSED_NO_TIME = "REFUSED_NO_TIME"
    #: This case has analysed as many documents today as it is allowed to.
    REFUSED_QUOTA = "REFUSED_QUOTA"
    #: This *user* has, across every case they own. Separate from the case limit because
    #: nothing bounds how many cases a person opens: 200 per case times an unbounded
    #: number of cases is an unbounded number of calls, so the per-case limit alone
    #: cannot bound a user.
    #:
    #: All three refusals are told apart on purpose. "This case has had its share",
    #: "you have had your share" and "nobody gets any more today" have different causes
    #: and different remedies, and giving someone the last when the first is true blames
    #: the system for their own retry loop.
    REFUSED_USER_QUOTA = "REFUSED_USER_QUOTA"


#: Statuses in which the capability produced a usable answer.
PRODUCTIVE_STATUSES = frozenset({ExtractionRunStatus.SUCCEEDED, ExtractionRunStatus.ABSTAINED})

#: What a user is told when analysis did not produce an answer.
#:
#: Lives here, beside the statuses, rather than being copied onto the processing run:
#: the status is the reason, and one source for it means two rows cannot disagree about
#: one event. Every sentence names what happened, what survived, and what the person can
#: do — "processing failed" would send someone to re-upload a document that is fine.
#:
#: Total over the non-productive statuses, checked by `tests/ai/test_classification.py`,
#: so a new status cannot ship without deciding what it says to a user.
SUMMARY_FOR_STATUS: dict[ExtractionRunStatus, str] = {
    ExtractionRunStatus.REFUSED_NO_BUDGET: (
        "Automatic analysis is paused until tomorrow because today's processing limit "
        "was reached. Your document was read and stored, and nothing was lost."
    ),
    ExtractionRunStatus.REFUSED_NO_TIME: (
        "There was not enough time to analyse this document. It was read and stored, "
        "and you can retry the analysis."
    ),
    ExtractionRunStatus.FAILED: (
        "Your document was read and stored, but automatic analysis did not complete. "
        "You can retry it."
    ),
    ExtractionRunStatus.REFUSED_QUOTA: (
        "This case has reached its daily limit for automatic document analysis. Your "
        "document was read and stored, and analysis can be retried tomorrow."
    ),
    ExtractionRunStatus.REFUSED_USER_QUOTA: (
        "You have reached your daily limit for automatic document analysis across all "
        "your cases. Your document was read and stored, and analysis can be retried "
        "tomorrow."
    ),
}

#: Refusals that happen before any provider call, so they can carry no `ModelRun`.
#: Named once here because migration 0029's CHECK constraint says the same thing in SQL,
#: and `tests/ai/test_extraction_run_statuses.py` asserts the two agree — the previous
#: quota status was added to this enum with no migration at all, which made every
#: refusal an `IntegrityError` the moment one was written.
PRE_DIAL_REFUSALS = frozenset(
    {
        ExtractionRunStatus.REFUSED_NO_BUDGET,
        ExtractionRunStatus.REFUSED_NO_TIME,
        ExtractionRunStatus.REFUSED_QUOTA,
        ExtractionRunStatus.REFUSED_USER_QUOTA,
    }
)


def hash_input(text: str) -> str:
    """A digest of exactly what was sent to the model.

    Stored instead of the text (RFC §8's `input_hash`), so a reprocess can tell
    "the same bytes, read again" from "a different reading of a replaced file" without
    this table holding document content — which would put it back inside the surface
    `evidence_file_texts` was separated out to keep small.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    #: The tenant boundary. Present so this table is case-scoped, gets an RLS policy,
    #: and is removed when a case is deleted.
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    #: The *immutable file version* that was read, not the item. RFC §8: extraction
    #: targets a version, so a replaced file gets its own runs and the old ones stay
    #: true about the bytes they saw.
    evidence_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evidence_files.id"))
    #: The pipeline execution this ran inside, so a document's whole processing story
    #: is one join rather than a timestamp correlation.
    processing_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_processing_runs.id"), index=True
    )
    #: Null when the invocation was refused before it was made — the ceiling, or the
    #: task deadline. The run still exists to record that nothing happened, and why.
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("model_runs.id"))

    capability: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    #: SHA-256 of the text sent to the model. See `hash_input`.
    input_hash: Mapped[str] = mapped_column(String(64))
    #: How many characters were sent, which with `input_hash` is enough to tell a
    #: truncated reading from a whole one without storing either.
    input_characters: Mapped[int] = mapped_column(Integer)

    # --- the classifier's finding -------------------------------------------------
    #: A `ClassifiedCategory`. Null when the run produced no answer. **Never written
    #: onto `EvidenceItem.category`**, which is the user's own choice.
    classified_category: Mapped[str | None] = mapped_column(String(30))
    #: Display metadata. Nothing branches on it (RFC §36).
    classification_confidence: Mapped[float | None] = mapped_column()
    #: The model's one-sentence justification, shown beside the category. Bounded at
    #: the schema and again here: it is the only free text the model controls that
    #: reaches a screen.
    classification_reasoning: Mapped[str | None] = mapped_column(String(300))

    #: Set in Python, not by `func.now()`.
    #:
    #: Postgres evaluates `now()` as the *transaction* timestamp, and this row's
    #: transaction begins at the commit **after** the provider call — while
    #: `completed_at` is captured before it. Every row therefore claimed to have started
    #: after it finished, and since this column orders `latest_classification`, the
    #: newest run was decided by a clock reading the wrong moment. Two runs written in
    #: one transaction (slice 3a: classify, then extract) would also have tied exactly,
    #: making `.limit(1)` a coin toss.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @classmethod
    def record(
        cls,
        *,
        case_id: uuid.UUID,
        evidence_item_id: uuid.UUID,
        evidence_file_id: uuid.UUID,
        processing_run_id: uuid.UUID,
        capability: str,
        status: ExtractionRunStatus,
        input_text: str,
        started_at: datetime,
        model_run_id: uuid.UUID | None = None,
        classified_category: str | None = None,
        classification_confidence: float | None = None,
        classification_reasoning: str | None = None,
    ) -> "ExtractionRun":
        """Build a settled run. There is no `start()`/`finish()` pair on purpose: a run
        is written once, when its outcome is known, so there is no half-written row for
        a reader to interpret and no in-place edit to make it immutable-by-convention
        rather than by construction."""
        return cls(
            case_id=case_id,
            evidence_item_id=evidence_item_id,
            evidence_file_id=evidence_file_id,
            processing_run_id=processing_run_id,
            model_run_id=model_run_id,
            capability=capability,
            status=status.value,
            input_hash=hash_input(input_text),
            input_characters=len(input_text),
            classified_category=classified_category,
            classification_confidence=classification_confidence,
            classification_reasoning=classification_reasoning,
            started_at=started_at,
            completed_at=utcnow(),
        )
