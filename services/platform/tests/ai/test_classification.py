"""DocumentClassifier: what it proposes, what it refuses to touch, and every way it
can fail without leaving a document stranded.

The claim this slice rests on is that a model output can be *shown* without being
*trusted*. Most of what is asserted here is therefore about what does not happen: the
user's category is not overwritten, no claim is created, no confidence gates anything,
and no failure path leaves a document in a state nothing can move it out of.
"""

import inspect
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import classification_service
from app.ai.classification_service import classify
from app.ai.classifier import (
    EXTRACTABLE,
    MAX_INPUT_CHARACTERS,
    ClassificationOutput,
    ClassifiedCategory,
)
from app.ai.domain import Capability, ModelRun, ModelRunStatus
from app.ai.extraction_run import (
    PRODUCTIVE_STATUSES,
    SUMMARY_FOR_STATUS,
    ExtractionRun,
    ExtractionRunStatus,
    hash_input,
)
from app.ai.fake import FakeProvider, failed, succeeded
from app.ai.service import AiBudget
from app.core.config import Settings

pytestmark = pytest.mark.integration

_IDS: dict[str, uuid.UUID] = {
    "case_id": uuid.uuid4(),
    "evidence_item_id": uuid.uuid4(),
    "evidence_file_id": uuid.uuid4(),
    "processing_run_id": uuid.uuid4(),
}


def _classify(
    provider: FakeProvider,
    settings: Settings,
    session: Session,
    *,
    text: str = "A booking confirmation.",
    budget_seconds: float = 30.0,
) -> classification_service.ClassificationOutcome:
    return classify(
        provider,
        session,
        document_text=text,
        budget=AiBudget(seconds=budget_seconds),
        settings=settings,
        trace_id="trace-x",
        **_IDS,
    )


def _output(category: ClassifiedCategory, confidence: float = 0.95) -> ClassificationOutput:
    return ClassificationOutput(category=category, confidence=confidence, reasoning="a reason")


# --- the happy path ----------------------------------------------------------------


def test_a_supported_document_is_classified_and_recorded(
    db_session: Session, ai_settings: Settings
) -> None:
    provider = FakeProvider(responses=[succeeded(_output(ClassifiedCategory.TRAVEL_SUPPORT))])
    outcome = _classify(provider, ai_settings, db_session)

    assert outcome.category is ClassifiedCategory.TRAVEL_SUPPORT
    assert outcome.run.status == ExtractionRunStatus.SUCCEEDED.value
    assert outcome.run.classified_category == "TRAVEL_SUPPORT"
    assert outcome.run.model_run_id is not None
    assert outcome.run.classification_confidence == 0.95


@pytest.mark.parametrize("category", [ClassifiedCategory.UNSUPPORTED, ClassifiedCategory.AMBIGUOUS])
def test_declining_to_choose_is_recorded_as_abstention_not_failure(
    db_session: Session, ai_settings: Settings, category: ClassifiedCategory
) -> None:
    """AI_EVALUATION_PLAN §3.2: correct abstention is a success. Recorded under its own
    status so it can be *measured* — folded into SUCCEEDED it would be invisible, and
    folded into FAILED it would look like something went wrong."""
    provider = FakeProvider(responses=[succeeded(_output(category))])
    outcome = _classify(provider, ai_settings, db_session)

    assert outcome.run.status == ExtractionRunStatus.ABSTAINED.value
    assert outcome.category is category
    assert outcome.produced_an_answer


# --- what it must not do ------------------------------------------------------------


def test_the_service_never_writes_the_users_category() -> None:
    """`EvidenceItem.category` is what the person chose at upload. The model's answer is
    a proposal; a disagreement is a thing to show them, not to resolve for them.

    Structural, because a behavioural test would only cover the paths it happened to
    exercise: nothing in this module or in the pipeline's analysis stage may assign to
    `item.category` at all.
    """
    import re

    # The *assignment*, not the phrase: both modules discuss `item.category` in prose,
    # and a substring check on the name flagged its own docstring.
    assignment = re.compile(r"\bitem\.category\s*=(?!=)")
    for name, source in (
        ("classification_service", inspect.getsource(classification_service)),
        (
            "_analyse",
            inspect.getsource(
                __import__("app.evidence.processing", fromlist=["_analyse"])._analyse
            ),
        ),
    ):
        assert not assignment.search(source), (
            f"{name} assigns to item.category — the classifier's answer is being written "
            "over the category the user chose at upload"
        )


def test_no_claim_or_fact_type_is_reachable_from_the_classifier() -> None:
    """Slice 2 creates no claims. A category is routing metadata: no requirement reads
    it, no assessment depends on it, and there is nothing in the fact model it could be
    confirmed into."""
    source = inspect.getsource(classification_service)
    for forbidden in ("ExtractedClaim", "FactVersion", "CaseFact", "ClaimReviewDecision"):
        assert forbidden not in source


def test_confidence_gates_nothing() -> None:
    """RFC §36: model confidence never grants additional authority. A threshold here
    would be a model deciding its own review requirement."""
    source = inspect.getsource(classification_service)
    assert "confidence >" not in source
    assert "confidence <" not in source
    assert "confidence >=" not in source


def test_a_low_confidence_answer_is_still_recorded_as_an_answer(
    db_session: Session, ai_settings: Settings
) -> None:
    """The behavioural half of the test above: 0.01 confidence is still a proposal, shown
    with its qualifier, not silently discarded."""
    provider = FakeProvider(
        responses=[succeeded(_output(ClassifiedCategory.IMMIGRATION_STATUS, confidence=0.01))]
    )
    outcome = _classify(provider, ai_settings, db_session)
    assert outcome.category is ClassifiedCategory.IMMIGRATION_STATUS
    assert outcome.run.status == ExtractionRunStatus.SUCCEEDED.value


def test_abstentions_select_no_extractor() -> None:
    """`EXTRACTABLE` is what slice 3a will use to pick a schema. `UNSUPPORTED` and
    `AMBIGUOUS` are absent by construction, so a document nobody could classify cannot
    have its fields read out under a guess."""
    assert ClassifiedCategory.UNSUPPORTED not in EXTRACTABLE
    assert ClassifiedCategory.AMBIGUOUS not in EXTRACTABLE
    assert len(EXTRACTABLE) == 4


# --- every failure ends in a state --------------------------------------------------


def test_a_spent_budget_is_a_state_not_an_exception(
    db_session: Session, ai_settings: Settings
) -> None:
    """The pipeline must never receive an exception it could forget to catch, or a
    document sits in ANALYSING with nothing left to move it — the UI says "analysing",
    the truth is "nothing will ever happen", and only a log knows."""
    from datetime import UTC, datetime

    from app.ai import spend
    from app.shared.db import get_sessionmaker

    settings = Settings(
        environment="test",
        ai_provider="fake",
        ai_daily_spend_ceiling_usd=0.01,
        ai_request_timeout_seconds=5.0,
        ai_task_deadline_seconds=30.0,
    )
    # Committed on its own connection: `invoke` opens a fresh session for the ledger, so
    # a spend written inside this test's uncommitted transaction would be invisible to
    # the check under test.
    with get_sessionmaker()() as ledger_session:
        spend.record(ledger_session, at=datetime.now(UTC), cost_usd=1.0)
        ledger_session.commit()

    provider = FakeProvider(responses=[])
    outcome = classify(
        provider,
        db_session,
        document_text="x",
        budget=AiBudget(seconds=30.0),
        settings=settings,
        **_IDS,  # type: ignore[arg-type]
    )
    assert provider.calls == [], "the provider must not be reached once the ceiling is met"
    assert outcome.run.status == ExtractionRunStatus.REFUSED_NO_BUDGET.value
    assert outcome.category is None
    assert outcome.run.model_run_id is None, "nothing was dialled, so there is no model run"
    assert outcome.user_summary and "paused until tomorrow" in outcome.user_summary


def test_an_exhausted_task_deadline_is_a_state(db_session: Session, ai_settings: Settings) -> None:
    outcome = _classify(FakeProvider(responses=[]), ai_settings, db_session, budget_seconds=0.5)
    assert outcome.run.status == ExtractionRunStatus.REFUSED_NO_TIME.value
    assert outcome.category is None
    assert outcome.run.model_run_id is None, "nothing was dialled, so there is no model run"
    assert outcome.user_summary and "retry" in outcome.user_summary


def test_a_provider_failure_invents_no_category(db_session: Session, ai_settings: Settings) -> None:
    provider = FakeProvider(responses=[failed(ModelRunStatus.INVALID_OUTPUT, attempts=3)])
    outcome = _classify(provider, ai_settings, db_session)

    assert outcome.run.status == ExtractionRunStatus.FAILED.value
    assert outcome.run.classified_category is None
    assert outcome.category is None
    assert outcome.run.model_run_id is not None, "the provider was reached; the run exists"


def test_a_refusal_invents_no_category(db_session: Session, ai_settings: Settings) -> None:
    """AI_EVALUATION_PLAN §8.14: a refusal is a recoverable state and never a
    fabricated fallback."""
    outcome = _classify(
        FakeProvider(responses=[failed(ModelRunStatus.REFUSED)]), ai_settings, db_session
    )
    assert outcome.run.status == ExtractionRunStatus.FAILED.value
    assert outcome.category is None


def test_every_unproductive_status_has_something_to_say_to_a_user() -> None:
    """A state with no sentence is a dead end. Total over the non-productive statuses so
    a new one cannot ship without deciding what it tells someone."""
    unproductive = set(ExtractionRunStatus) - PRODUCTIVE_STATUSES
    assert set(SUMMARY_FOR_STATUS) == unproductive
    for status, sentence in SUMMARY_FOR_STATUS.items():
        assert "read and stored" in sentence, f"{status.value} does not say what survived"


# --- what the model is given --------------------------------------------------------


def test_the_input_is_capped(db_session: Session, ai_settings: Settings) -> None:
    """A classifier is decided by the top of a document. Sending all 200,000 characters
    `extraction.py` permits would cost ~40x the spike's per-document figure for the same
    answer."""
    provider = FakeProvider(responses=[succeeded(_output(ClassifiedCategory.TRAVEL_SUPPORT))])
    _classify(provider, ai_settings, db_session, text="A" * 100_000)

    (_capability, _system, sent) = provider.calls[0]
    assert len(sent) == MAX_INPUT_CHARACTERS


def test_the_filename_is_never_sent(ai_settings: Settings) -> None:
    """MVP §8.10's misleading-filename criterion, met by omission rather than by
    instructing the model to ignore it. A document named `settled-status.pdf` containing
    a restaurant menu must be classified on the menu."""
    signature = inspect.signature(classify).parameters
    assert "filename" not in signature
    assert "original_filename" not in signature
    assert "display_name" not in signature


def test_the_declared_category_is_never_sent(ai_settings: Settings) -> None:
    """Sending the user's own answer would invite the model to agree with it, and an
    agreement that was primed is not a corroboration."""
    assert "category" not in inspect.signature(classify).parameters


def test_the_run_records_a_hash_of_exactly_what_was_sent(
    db_session: Session, ai_settings: Settings
) -> None:
    provider = FakeProvider(responses=[succeeded(_output(ClassifiedCategory.TRAVEL_SUPPORT))])
    outcome = _classify(provider, ai_settings, db_session, text="B" * 50_000)

    (_capability, _system, sent) = provider.calls[0]
    assert outcome.run.input_hash == hash_input(sent)
    assert outcome.run.input_characters == len(sent)


# --- persistence --------------------------------------------------------------------


def test_the_run_persists_with_its_model_run(
    db_session: Session, ledger: object, ai_settings: Settings
) -> None:
    """The ADR-0025 join: the domain run points at the telemetry row, not the other way
    round, so `model_runs` stays out of the case-scoped closure."""
    from app.cases.domain import ApplicationCase  # noqa: F401 — FK targets must exist

    provider = FakeProvider(responses=[succeeded(_output(ClassifiedCategory.LIFE_IN_THE_UK))])
    outcome = classify(
        provider,
        db_session,
        document_text="Life in the UK test pass notification.",
        budget=AiBudget(seconds=30.0),
        settings=ai_settings,
        **_IDS,  # type: ignore[arg-type]
    )
    model_runs = list(db_session.execute(select(ModelRun)).scalars())
    assert len(model_runs) == 1
    assert outcome.run.model_run_id == model_runs[0].id
    assert ExtractionRun.__table__.foreign_keys, "extraction_runs must reference model_runs"


def test_the_capability_is_recorded_on_the_run(db_session: Session, ai_settings: Settings) -> None:
    provider = FakeProvider(responses=[succeeded(_output(ClassifiedCategory.ENGLISH_LANGUAGE))])
    outcome = _classify(provider, ai_settings, db_session)
    assert outcome.run.capability == Capability.DOCUMENT_CLASSIFIER.value
