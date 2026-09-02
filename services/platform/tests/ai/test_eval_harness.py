"""The eval harness's foundation: it can read the corpus, and it can tell when the
corpus is broken.

The second half is the point. A manifest naming a document that does not exist would
otherwise surface as a confusing *model* result, and the M8 spike is the reason to
care: its first run reported the model correctly abstaining when in fact every call
had failed (AI_SPIKE_FINDINGS §5). A harness that cannot distinguish "the fixture is
broken" from "the model was wrong" will eventually report the second when it means
the first.
"""

import pathlib

import pytest
from evals.runner import Fixture, check_manifests, load_fixtures


@pytest.fixture(scope="module", autouse=True)
def _documents() -> None:
    """The fixture PDFs are generated, not committed (see `evals/README.md`), so a
    clean checkout has none until something makes them."""
    from evals.fixtures import make_documents

    for name, lines in make_documents.DOCUMENTS.items():
        (make_documents.OUT / name).parent.mkdir(parents=True, exist_ok=True)
        make_documents.write(name, lines)


def _fixture(**overrides: object) -> Fixture:
    base: dict[str, object] = {
        "id": "x_001",
        "capability": "TravelRecordExtractor",
        "document": "fixtures/travel/italy_booking_amended_return.pdf",
        "tags": (),
        "expected": {},
        "must_not_extract": {},
        "risk": "HIGH",
        "notes": "",
        "source_manifest": "travel_extractor.jsonl",
    }
    base.update(overrides)
    return Fixture(**base)  # type: ignore[arg-type]


def test_the_committed_corpus_is_coherent() -> None:
    """The check `just eval` runs. Fails on a manifest referencing a document that
    was renamed, an id reused, or an expectation contradicting its own forbidden list."""
    problems = check_manifests(load_fixtures())
    assert problems.ok, (
        f"missing={problems.missing_documents} duplicates={problems.duplicate_ids} "
        f"contradictory={problems.contradictory_expectations} risk={problems.unknown_risk}"
    )


def test_every_fixture_names_a_document_that_exists() -> None:
    for fixture in load_fixtures():
        assert fixture.document_path.is_file(), f"{fixture.id} -> {fixture.document}"


def test_a_missing_document_is_reported() -> None:
    problems = check_manifests([_fixture(document="fixtures/travel/not_here.pdf")])
    assert problems.missing_documents == ["x_001 -> fixtures/travel/not_here.pdf"]
    assert not problems.ok


def test_a_duplicate_id_is_reported() -> None:
    problems = check_manifests([_fixture(), _fixture()])
    assert problems.duplicate_ids == ["x_001"]


def test_an_expectation_that_contradicts_its_own_forbidden_list_is_reported() -> None:
    """The authoring error that would look most like a model failure: a fixture that
    expects the value it also forbids can never pass, and the report would blame the
    model every run."""
    problems = check_manifests(
        [
            _fixture(
                expected={"journeys.0.arrival_return.date_iso": "2026-05-11"},
                must_not_extract={"any_date": ["2026-05-11"]},
            )
        ]
    )
    assert len(problems.contradictory_expectations) == 1
    assert "2026-05-11" in problems.contradictory_expectations[0]


def test_an_unknown_risk_level_is_reported() -> None:
    """`risk` drives whether a failure is averaged into a headline or blocks a release
    (§3.4, §12). A typo here silently downgrades a safety-critical fixture."""
    assert check_manifests([_fixture(risk="CRITICAL")]).unknown_risk == ["x_001 -> CRITICAL"]


def test_every_injection_fixture_is_high_risk() -> None:
    """§19 makes injection-driven authority escalation a zero-tolerance gate. A fixture
    marked anything less would let it be averaged into a headline (§3.4)."""
    injection = [f for f in load_fixtures() if "prompt_injection" in f.tags]
    assert injection, "the corpus has no prompt-injection fixture"
    for fixture in injection:
        assert fixture.risk == "HIGH", f"{fixture.id} is {fixture.risk}"


def test_the_injection_extractor_fixture_forbids_the_injected_values() -> None:
    """Only the *extractor* fixture can carry a forbidden list — a classifier's output
    is one category, so "must not extract" has nothing to bite on there. Its injection
    fixture asserts the category is unchanged instead, which is the whole of what the
    classifier could get wrong."""
    extractor = [
        f
        for f in load_fixtures()
        if "prompt_injection" in f.tags and f.capability != "DocumentClassifier"
    ]
    assert extractor, "no extractor injection fixture"
    for fixture in extractor:
        forbidden = {v for values in fixture.must_not_extract.values() for v in values}
        assert "2018-01-01" in forbidden, "the injected grant date is not forbidden"
        assert any("confirmed" in v for v in forbidden), "no authority-escalation string forbidden"
        # And the positive half §14 requires: real extraction must still succeed, so a
        # model that "fails safe" by returning nothing has not passed.
        assert fixture.expected, f"{fixture.id} expects nothing; failing safe would pass"

    classifier = [
        f
        for f in load_fixtures()
        if "prompt_injection" in f.tags and f.capability == "DocumentClassifier"
    ]
    for fixture in classifier:
        assert fixture.expected.get("category") == "TRAVEL_SUPPORT"


def test_the_ambiguous_date_fixture_expects_a_null() -> None:
    """Blind confirmation of date fields rests on an ambiguous date not being silently
    resolved (AI_SPIKE_FINDINGS §3.1). Null is the pass condition, and a fixture that
    quietly gained a concrete expectation would remove the only test of that."""
    (fixture,) = [
        f
        for f in load_fixtures()
        if "ambiguous" in f.tags and f.capability == "TravelRecordExtractor"
    ]
    assert fixture.expected["journeys.0.departure.date_iso"] is None
    assert fixture.expected["journeys.0.arrival_return.date_iso"] is None


def test_the_classifier_still_calls_the_ambiguous_document_a_travel_booking() -> None:
    """The regression guard for AI_SPIKE_FINDINGS §3.2. When the date-ambiguity rule
    lived in the block every capability shared, the classifier answered AMBIGUOUS for
    this document 3 runs out of 3 — the extractor's question, answered by the wrong
    capability, which suppressed extraction entirely."""
    (fixture,) = [
        f for f in load_fixtures() if "ambiguous" in f.tags and f.capability == "DocumentClassifier"
    ]
    assert fixture.expected["category"] == "TRAVEL_SUPPORT"


def test_the_generated_documents_read_back_through_the_real_extractor() -> None:
    """The corpus is only meaningful if the pipeline can read it. Uses M7's own
    reader, not a separate one — the text a grader scores must be the text the product
    would have sent."""
    from app.evidence import extraction

    for fixture in load_fixtures():
        result = extraction.extract(pathlib.Path(fixture.document_path).read_bytes())
        assert result.has_text_layer, f"{fixture.id} has no readable text"
        assert result.character_count > 200, (
            f"{fixture.id} read only {result.character_count} chars"
        )
