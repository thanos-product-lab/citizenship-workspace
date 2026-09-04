"""Regression tests for what the slice-2 reviews found.

Six findings, two of which both reviewers reached independently. Each was a real defect
in the first version of the slice, and each is here because a defect fixed without a
test is a defect waiting for the next refactor.
"""

import inspect
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.classification_service import classify
from app.ai.classifier import EXTRACTABLE, ClassificationOutput, ClassifiedCategory, ExtractorKey
from app.ai.extraction_run import SUMMARY_FOR_STATUS, ExtractionRun, ExtractionRunStatus
from app.ai.fake import FakeProvider, succeeded
from app.ai.repository import ExtractionRunRepository
from app.ai.service import AiBudget
from app.core.config import Settings
from app.evidence.domain import EvidenceCategory
from app.evidence.extraction import DEADLINE_SECONDS

pytestmark = pytest.mark.integration


@dataclass
class _Chain:
    """A real case, document and processing run.

    Random uuids used to be enough here. They no longer are, and that is migration 0028
    doing its job twice over: the RLS policy predicates on `extraction_runs.case_id`, so
    a run naming a case that does not exist cannot be inserted by the request role, and
    the composite foreign key insists the evidence item really does belong to the case
    the run claims.
    """

    case_id: uuid.UUID
    evidence_item_id: uuid.UUID
    evidence_file_id: uuid.UUID
    processing_run_id: uuid.UUID


def _a_chain(session: Session) -> _Chain:
    from app.cases.domain import ApplicationCase
    from app.evidence.domain import (
        PIPELINE_VERSION,
        EvidenceFile,
        EvidenceItem,
        EvidenceProcessingRun,
        ProcessingRunStatus,
    )
    from app.evidence.domain import (
        EvidenceCategory as _Category,
    )

    case = ApplicationCase.create(owner_user_id="user_a", title="Quota")
    session.add(case)
    session.flush()

    item = EvidenceItem.uploaded(
        case_id=case.id,
        category=_Category.TRAVEL_SUPPORT,
        display_name="A document",
        created_by="user_a",
    )
    session.add(item)
    session.flush()

    file = EvidenceFile(
        evidence_item_id=item.id,
        storage_key=f"k/{uuid.uuid4()}",
        original_filename="doc.pdf",
        media_type="application/pdf",
        size_bytes=1024,
        checksum="x" * 64,
        version_number=1,
        uploaded_at=datetime.now(UTC),
    )
    session.add(file)
    session.flush()
    item.current_file_id = file.id

    run = EvidenceProcessingRun(
        evidence_item_id=item.id,
        evidence_file_id=file.id,
        status=ProcessingRunStatus.SUCCEEDED.value,
        pipeline_version=PIPELINE_VERSION,
        completed_at=datetime.now(UTC),
        idempotency_key=f"quota-{uuid.uuid4()}",
    )
    session.add(run)
    session.flush()
    return _Chain(case.id, item.id, file.id, run.id)


def _output(
    category: ClassifiedCategory = ClassifiedCategory.TRAVEL_SUPPORT,
) -> ClassificationOutput:
    return ClassificationOutput(category=category, confidence=0.9, reasoning="a reason")


# --- the budget could outlive the task ---------------------------------------------


def test_the_ai_budget_and_the_text_deadline_fit_inside_celerys_soft_limit() -> None:
    """The arithmetic error the security review caught, as an assertion.

    A budget constructed just before the model call gives a *fresh* allowance, so
    `extraction.DEADLINE_SECONDS` (20s) plus a full AI budget (45s) is 65 seconds inside
    a task Celery kills at 60. The check would have permitted a call it had no time for,
    `SoftTimeLimitExceeded` would fire mid-request, and `invoke`'s `finally` would record
    the run with `estimated_cost_usd = 0` — a request that was issued and billed, counted
    as free against the ceiling built to bound exactly that loop.
    """
    from worker.celery_app import celery_app

    settings = Settings()
    soft_limit = celery_app.conf.task_soft_time_limit

    # The invariant is over the budget *alone*, and only because the budget is now started
    # at task entry — so extraction's twenty seconds are spent inside it rather than
    # before it, and `AiBudget.check` refuses a call whose timeout would outlast what is
    # left. A task therefore cannot exceed `ai_task_deadline_seconds` of wall clock in AI
    # work no matter how slow the parser was.
    #
    # Adding `DEADLINE_SECONDS` here would encode the *old* arrangement, where the budget
    # was constructed fresh at the model call and the two bounds genuinely summed.
    assert settings.ai_task_deadline_seconds < soft_limit, (
        f"the AI budget ({settings.ai_task_deadline_seconds}s) must fit inside Celery's "
        f"soft limit ({soft_limit}s) with headroom, or a task is killed mid-request and "
        "the spend goes unrecorded"
    )
    # And the budget has to leave room for extraction to finish and one call to run.
    assert (
        DEADLINE_SECONDS + settings.ai_request_timeout_seconds < settings.ai_task_deadline_seconds
    ), "the budget cannot accommodate a slow parse followed by one model call"


def test_the_budget_is_started_at_task_entry_not_at_the_model_call() -> None:
    """Structural, because the arithmetic above only holds if the budget actually
    measures the whole task. Constructed inside `_analyse`, it would reset after
    extraction had already spent twenty seconds of the same task."""
    from app.evidence import processing

    assert "budget = AiBudget(" in inspect.getsource(processing.validate_evidence)
    assert "AiBudget(" not in inspect.getsource(processing._analyse), (
        "_analyse builds its own budget, so the clock restarts after extraction"
    )


# --- deletion left a fingerprint and a quoted fragment behind ------------------------


def test_deletion_clears_the_input_hash_and_the_model_prose(db_session: Session) -> None:
    """Both reviews found this. `purge.py` already clears `checksum` because it is a
    *content fingerprint* — `input_hash` is the same fingerprint over the same document,
    one table over, and `classification_reasoning` is model prose the prompt explicitly
    permits to quote from the document."""
    source = inspect.getsource(__import__("app.evidence.purge", fromlist=["_tombstone"])._tombstone)
    assert "run.input_hash" in source
    assert "run.classification_reasoning = None" in source
    # The category stays: six enum values are not a fingerprint, and the CHECK constraint
    # requires a settled run to say what it concluded.
    assert "run.classified_category = None" not in source


# --- the model's answer was one expression from the user's category -----------------


def test_the_extractor_key_cannot_be_assigned_to_the_users_category() -> None:
    """`EXTRACTABLE` used to map to `EvidenceCategory`, which made `EXTRACTABLE[answer]`
    exactly the value someone would assign to `item.category` — the one thing this slice
    forbids, one expression away, guarded only by a regex over two named modules.

    Now it yields an `ExtractorKey`, a different type mypy refuses to assign there. A
    type error rather than a guard someone can delete.
    """
    for value in EXTRACTABLE.values():
        assert isinstance(value, ExtractorKey)
        assert value.value not in {c.value for c in EvidenceCategory}, (
            f"{value!r} shares a wire value with EvidenceCategory, so a string round-trip "
            "would silently convert one into the other"
        )


# --- model free text is bounded by a character count that cannot see what matters ----


@pytest.mark.parametrize(
    ("hostile", "must_not_contain"),
    [
        ("Confirmed.‮DESREVER text", "‮"),
        ("Zero​width‍joiner", "​"),
        ("Line one\nLine two\n\nLine three", "\n"),
        ("Tab\there", "\t"),
        ("﻿byte order mark", "﻿"),
    ],
)
def test_the_reasoning_field_strips_what_a_length_cap_cannot_see(
    hostile: str, must_not_contain: str
) -> None:
    """`max_length=300` counts *characters*, so a bidi override, a zero-width joiner and
    forty newlines all fit inside it comfortably.

    React escapes markup, which is the risk people think of and not the one that applies:
    the exposure is a model that has just read a hostile document emitting a plausible,
    product-voiced sentence into a muted line of UI. Direction overrides and invisible
    characters make that easier to stage and impossible to catch in review.
    """
    output = ClassificationOutput(
        category=ClassifiedCategory.TRAVEL_SUPPORT, confidence=0.5, reasoning=hostile
    )
    assert must_not_contain not in output.reasoning
    assert output.reasoning == " ".join(output.reasoning.split()), "whitespace not collapsed"


def test_the_reasoning_field_is_not_projected_over_http() -> None:
    """The highest-risk field the classifier produces, and nothing renders it. Shipping
    it to the browser for no reader is the surface M7 removed the extraction excerpt to
    avoid. Slice 3b adds it back with the review surface and explicit attribution."""
    from app.evidence.schemas import EvidenceResponse

    assert "proposed_category_reasoning" not in EvidenceResponse.model_fields


# --- a run claimed to start after it finished ---------------------------------------


def test_a_run_starts_before_it_finishes(db_session: Session, ai_settings: Settings) -> None:
    """`server_default=func.now()` is the *transaction* timestamp, and this row's
    transaction begins at the commit after the provider call — while `completed_at` is
    captured before it. Every row claimed to have started after it finished, and
    `started_at` orders `latest_classification`."""
    outcome = classify(
        FakeProvider(responses=[succeeded(_output())]),
        db_session,
        case_id=uuid.uuid4(),
        evidence_item_id=uuid.uuid4(),
        evidence_file_id=uuid.uuid4(),
        processing_run_id=uuid.uuid4(),
        document_text="A booking.",
        budget=AiBudget(seconds=30.0),
        settings=ai_settings,
    )
    assert outcome.run.completed_at is not None
    assert outcome.run.started_at <= outcome.run.completed_at


# --- one case could exhaust the whole deployment's budget ---------------------------


def test_a_case_that_has_used_its_daily_allowance_is_refused(
    db_session: Session, ai_settings: Settings
) -> None:
    """The deployment ceiling bounds the *bill*; this bounds one case's share of it.

    Without it, a retry loop on a single document is three billable requests every
    thirty seconds — about 8,600 a day — and the first tenant to run one exhausts the
    shared ceiling, putting every other user's documents into `REFUSED_NO_BUDGET` until
    midnight. That turns a cost problem into a cross-tenant availability problem.
    """
    chain = _a_chain(db_session)
    case_id = chain.case_id
    settings = ai_settings.model_copy(update={"ai_case_daily_call_limit": 2})

    provider = FakeProvider(responses=[succeeded(_output()), succeeded(_output())])
    for _ in range(2):
        outcome = classify(
            provider,
            db_session,
            case_id=case_id,
            evidence_item_id=chain.evidence_item_id,
            evidence_file_id=chain.evidence_file_id,
            processing_run_id=chain.processing_run_id,
            document_text="A booking.",
            budget=AiBudget(seconds=30.0),
            settings=settings,
        )
        db_session.add(outcome.run)
    db_session.flush()

    refused = classify(
        provider,
        db_session,
        case_id=case_id,
        evidence_item_id=chain.evidence_item_id,
        evidence_file_id=chain.evidence_file_id,
        processing_run_id=chain.processing_run_id,
        document_text="A booking.",
        budget=AiBudget(seconds=30.0),
        settings=settings,
    )

    assert refused.run.status == ExtractionRunStatus.REFUSED_QUOTA.value
    assert refused.category is None
    assert refused.run.model_run_id is None, "nothing was dialled"
    assert provider.calls and len(provider.calls) == 2, "the third call reached the provider"


def test_the_quota_counts_refusals_too(db_session: Session) -> None:
    """A loop that keeps being refused is still a loop. A counter that only saw the
    successful calls would reset itself the moment the quota started working."""
    chain = _a_chain(db_session)
    case_id = chain.case_id
    now = datetime.now(UTC)
    for status in (ExtractionRunStatus.SUCCEEDED, ExtractionRunStatus.FAILED):
        db_session.add(
            ExtractionRun.record(
                case_id=case_id,
                evidence_item_id=chain.evidence_item_id,
                evidence_file_id=chain.evidence_file_id,
                processing_run_id=chain.processing_run_id,
                capability="DocumentClassifier",
                status=status,
                input_text="x",
                started_at=now,
                classified_category="TRAVEL_SUPPORT"
                if status is ExtractionRunStatus.SUCCEEDED
                else None,
            )
        )
    db_session.flush()

    assert ExtractionRunRepository.calls_today(db_session, case_id=case_id, at=now) == 2


def test_the_quota_window_rolls(db_session: Session) -> None:
    chain = _a_chain(db_session)
    case_id = chain.case_id
    now = datetime.now(UTC)
    db_session.add(
        ExtractionRun.record(
            case_id=case_id,
            evidence_item_id=chain.evidence_item_id,
            evidence_file_id=chain.evidence_file_id,
            processing_run_id=chain.processing_run_id,
            capability="DocumentClassifier",
            status=ExtractionRunStatus.FAILED,
            input_text="x",
            started_at=now - timedelta(days=2),
        )
    )
    db_session.flush()
    assert ExtractionRunRepository.calls_today(db_session, case_id=case_id, at=now) == 0


def test_the_quota_refusal_says_it_is_this_case_not_the_system(db_session: Session) -> None:
    """ "You have had your share" and "nobody gets any more" are different sentences, and
    giving a user the second when the first is true blames the system for their loop."""
    quota = SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_QUOTA]
    ceiling = SUMMARY_FOR_STATUS[ExtractionRunStatus.REFUSED_NO_BUDGET]
    assert "this case" in quota.casefold()
    assert quota != ceiling
    assert "read and stored" in quota


# --- the table's own guarantees -----------------------------------------------------


def test_extraction_runs_is_append_only_except_where_deletion_must_redact(
    db_session: Session,
) -> None:
    """0026 revoked UPDATE on `model_runs` because *"provenance a request path can rewrite
    is not provenance"*, and 0027 granted it on `extraction_runs` the very next migration.

    The revoke is column-level rather than total, because a blanket one collides with the
    deletion path: the purge must clear `input_hash` and `classification_reasoning`, and
    it runs as `app_rls` like every other case-scoped write. The grant says the real rule
    — redact what deletion obliges, rewrite nothing the run concluded.
    """
    assert (
        db_session.execute(
            text("SELECT has_table_privilege('app_rls', 'extraction_runs', 'UPDATE')")
        ).scalar_one()
        is False
    )

    def _writable(column: str) -> bool:
        return bool(
            db_session.execute(
                text("SELECT has_column_privilege('app_rls','extraction_runs',:c,'UPDATE')"),
                {"c": column},
            ).scalar_one()
        )

    # Erasable, because deletion is obliged to erase them.
    assert _writable("input_hash")
    assert _writable("classification_reasoning")
    # Provenance. A request path that could rewrite these could rewrite what the system
    # concluded about a document, when, and under which model.
    for column in ("classified_category", "status", "capability", "model_run_id", "started_at"):
        assert not _writable(column), f"{column} is rewritable by the request role"


def test_the_policy_predicates_on_the_column_the_queries_filter_on(
    db_session: Session,
) -> None:
    """The policy guarded `evidence_item_id` while every query filtered `case_id`, with
    nothing tying the two together. Not exploitable — both would have had to be wrong —
    but defence in depth is only worth having at depth."""
    predicate = db_session.execute(
        text("SELECT qual FROM pg_policies WHERE tablename = 'extraction_runs'")
    ).scalar_one()
    assert "case_id" in str(predicate)


def test_a_user_who_has_spread_their_calls_across_cases_is_still_refused(
    db_session: Session, ai_settings: Settings
) -> None:
    """The gap the per-case limit alone leaves.

    Nothing bounds how many cases a person opens, so 200 per case multiplied by an
    unbounded number of cases is an unbounded number of calls — and one account could
    still exhaust the deployment's daily ceiling and stop every other tenant's
    processing until midnight. Each case here is comfortably under its own limit; the
    user is not.
    """
    settings = ai_settings.model_copy(
        update={"ai_case_daily_call_limit": 100, "ai_user_daily_call_limit": 2}
    )
    first, second = _a_chain(db_session), _a_chain(db_session)

    provider = FakeProvider(responses=[succeeded(_output()), succeeded(_output())])
    for chain in (first, second):
        outcome = classify(
            provider,
            db_session,
            case_id=chain.case_id,
            evidence_item_id=chain.evidence_item_id,
            evidence_file_id=chain.evidence_file_id,
            processing_run_id=chain.processing_run_id,
            document_text="A booking.",
            budget=AiBudget(seconds=30.0),
            settings=settings,
        )
        assert outcome.produced_an_answer
        db_session.add(outcome.run)
    db_session.flush()

    # A third case, untouched, and well under its own limit of 100.
    third = _a_chain(db_session)
    refused = classify(
        provider,
        db_session,
        case_id=third.case_id,
        evidence_item_id=third.evidence_item_id,
        evidence_file_id=third.evidence_file_id,
        processing_run_id=third.processing_run_id,
        document_text="A booking.",
        budget=AiBudget(seconds=30.0),
        settings=settings,
    )

    assert refused.run.status == ExtractionRunStatus.REFUSED_USER_QUOTA.value
    assert refused.category is None
    assert refused.run.model_run_id is None, "nothing was dialled"
    assert len(provider.calls) == 2, "the third call reached the provider"


def test_one_users_calls_do_not_count_against_another(
    db_session: Session, ai_settings: Settings
) -> None:
    """A shared counter would make one busy tenant deny the service to everyone else —
    which is the failure the per-user limit exists to prevent, not to cause."""
    from app.ai.repository import ExtractionRunRepository
    from app.cases.domain import ApplicationCase
    from app.shared.tenant import clear_tenant, set_tenant

    mine = _a_chain(db_session)
    db_session.add(
        ExtractionRun.record(
            case_id=mine.case_id,
            evidence_item_id=mine.evidence_item_id,
            evidence_file_id=mine.evidence_file_id,
            processing_run_id=mine.processing_run_id,
            capability="DocumentClassifier",
            status=ExtractionRunStatus.SUCCEEDED,
            input_text="x",
            started_at=datetime.now(UTC),
            classified_category="TRAVEL_SUPPORT",
        )
    )
    # Flushed before the tenant changes. SQLAlchemy defers the INSERT until flush, so
    # switching first would send user_a's row under user_b's tenant and the policy would
    # refuse it — correctly, and for a reason that has nothing to do with this test.
    db_session.flush()

    # Switch tenant to create the other user's case: RLS correctly refuses to let
    # `user_a` insert a row owned by `user_b`, which is the policy doing its job.
    set_tenant(db_session, "user_b")
    theirs = ApplicationCase.create(owner_user_id="user_b", title="Someone else")
    db_session.add(theirs)
    db_session.flush()

    # Counted as the table owner, with no tenant at all. That is the point: the
    # repository *joins* on the owner rather than leaning on RLS to scope the count, and
    # this asserts the join is what does the work. A limit that silently becomes "no
    # limit" the day something runs as the owner is not a limit.
    clear_tenant(db_session)
    now = datetime.now(UTC)
    assert (
        ExtractionRunRepository.calls_today_for_the_owner_of(
            db_session, case_id=mine.case_id, at=now
        )
        == 1
    )
    assert (
        ExtractionRunRepository.calls_today_for_the_owner_of(db_session, case_id=theirs.id, at=now)
        == 0
    )
