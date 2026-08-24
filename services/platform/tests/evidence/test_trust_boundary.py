"""Extracted text cannot reach a conclusion.

Domain §15.1 says `EvidenceFileText` is never an assessed input. That sentence is only
worth the enforcement behind it, so this is the enforcement: structural checks that fail
if the type, the table, or the text itself finds a path into the assessment machinery.

The distinction being protected is the product's whole premise. Text read out of a
document is untrusted material — the same standing as the file it came from. It is not a
claim (it proposes nothing about the case) and it is not a fact (nobody confirmed it).
The moment it can influence a requirement's conclusion, the difference between "the
system read this" and "the system concluded this" has collapsed, and no amount of UI copy
puts it back.
"""

import pathlib

import pytest

pytestmark = pytest.mark.integration

_APP = pathlib.Path(__file__).resolve().parent.parent.parent / "app"

#: Modules that decide, or contribute to, a requirement's conclusion.
_ASSESSMENT_MODULES = ("assessments", "requirements", "issues", "residence", "applicants")


def _sources(package: str) -> list[pathlib.Path]:
    return sorted((_APP / package).rglob("*.py"))


def test_no_assessment_module_imports_the_extracted_text_type() -> None:
    """The cheapest possible check, and the one that catches it earliest.

    An evaluator cannot read a table it never imports the model for. If this ever needs
    to be relaxed, the thing being relaxed is Domain §15.1.
    """
    offenders = [
        f"{path.relative_to(_APP.parent)}"
        for package in _ASSESSMENT_MODULES
        for path in _sources(package)
        if "EvidenceFileText" in path.read_text()
    ]
    assert offenders == [], (
        f"assessment code referencing extracted document text: {offenders}. "
        "Domain §15.1: it is never an assessed input."
    )


def test_no_assessment_module_queries_the_table() -> None:
    """Belt and braces: raw SQL sidesteps the import check above."""
    offenders = [
        f"{path.relative_to(_APP.parent)}"
        for package in _ASSESSMENT_MODULES
        for path in _sources(package)
        if "evidence_file_texts" in path.read_text()
    ]
    assert offenders == [], f"assessment code querying evidence_file_texts: {offenders}"


def test_the_check_has_modules_to_check() -> None:
    """Guard against the packages moving and the assertions above passing vacuously —
    the lesson of `test_the_check_has_routes_to_check`, on a third derivation."""
    assert sum(len(_sources(package)) for package in _ASSESSMENT_MODULES) > 20


def test_no_rule_declares_a_dependency_on_extracted_text() -> None:
    """`DependencyInputKind` is the vocabulary of things that can invalidate a
    conclusion. There is deliberately no member for document text — `EVIDENCE_SUPPORT`
    (slice 4) is about a document *existing* and being linked, never about what it says.
    """
    from app.requirements.models import DependencyInputKind

    kinds = {kind.value for kind in DependencyInputKind}
    assert not any("TEXT" in kind or "CONTENT" in kind for kind in kinds), (
        f"a rule can declare a dependency on document content: {sorted(kinds)}"
    )


def test_the_api_never_projects_document_content() -> None:
    """The response model is the boundary. A field carrying text — full or excerpted —
    puts Tier-3 content in every library response, in the Next.js server's memory, and in
    any error reporter's breadcrumbs, for screens that only need to say extraction
    happened."""
    from app.evidence.schemas import EvidenceResponse

    fields = set(EvidenceResponse.model_fields)
    assert "content" not in fields
    assert "excerpt" not in fields
    assert "text" not in fields
    # What may cross: counts and flags about the file, never words from it.
    assert {"page_count", "pages_read", "character_count", "text_truncated"} <= fields
