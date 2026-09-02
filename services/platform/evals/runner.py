"""The evaluation harness, at its foundation.

`AI_EVALUATION_PLAN.md` §41 Phase 1. What exists today is the part that needs no
model: loading the manifests, and checking that what they claim is internally
coherent. Capability runners and graders arrive with the capabilities themselves
(§41 Phase 2), because a grader written before the thing it grades is a guess.

That is not as thin as it sounds. A manifest naming a document that does not exist,
or two fixtures sharing an id, or an `expected` value that is also listed under
`must_not_extract`, are all failures that would otherwise surface as a confusing
*model* result — and the M8 spike is the reason to take that seriously: its first run
reported the model correctly abstaining when in fact every call had failed
(AI_SPIKE_FINDINGS §5). A harness that cannot tell "the fixture is broken" from "the
model was wrong" will eventually tell you the second when it means the first.

Run with `just eval`.
"""

import json
import pathlib
import sys
from dataclasses import dataclass, field

EVALS_DIR = pathlib.Path(__file__).parent
MANIFEST_DIR = EVALS_DIR / "manifests"
FIXTURE_DIR = EVALS_DIR / "fixtures"


@dataclass(frozen=True)
class Fixture:
    """One manifest entry. Deliberately close to the file: the manifest is the
    contract (§7), and a loader that normalised it into something more convenient
    would put a translation between the contract and what is checked."""

    id: str
    capability: str
    document: str
    tags: tuple[str, ...]
    expected: dict[str, object]
    must_not_extract: dict[str, list[str]]
    risk: str
    notes: str
    source_manifest: str

    @property
    def document_path(self) -> pathlib.Path:
        return EVALS_DIR / self.document


@dataclass
class ManifestProblems:
    """What is wrong with the corpus itself, before any model is involved."""

    missing_documents: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    contradictory_expectations: list[str] = field(default_factory=list)
    unknown_risk: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (
            self.missing_documents
            or self.duplicate_ids
            or self.contradictory_expectations
            or self.unknown_risk
        )


_RISKS = {"HIGH", "MEDIUM", "LOW"}


def load_fixtures() -> list[Fixture]:
    fixtures: list[Fixture] = []
    for manifest in sorted(MANIFEST_DIR.glob("*.jsonl")):
        for line_number, line in enumerate(manifest.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"{manifest.name}:{line_number} is not valid JSON: {exc}"
                ) from None
            fixtures.append(
                Fixture(
                    id=row["id"],
                    capability=row["capability"],
                    document=row["document"],
                    tags=tuple(row.get("tags", ())),
                    expected=row.get("expected", {}),
                    must_not_extract=row.get("must_not_extract", {}),
                    risk=row.get("risk", "MEDIUM"),
                    notes=row.get("notes", ""),
                    source_manifest=manifest.name,
                )
            )
    return fixtures


def check_manifests(fixtures: list[Fixture]) -> ManifestProblems:
    problems = ManifestProblems()

    seen: set[str] = set()
    for fixture in fixtures:
        if fixture.id in seen:
            problems.duplicate_ids.append(fixture.id)
        seen.add(fixture.id)

        if not fixture.document_path.is_file():
            problems.missing_documents.append(f"{fixture.id} -> {fixture.document}")

        if fixture.risk not in _RISKS:
            problems.unknown_risk.append(f"{fixture.id} -> {fixture.risk}")

        # An expected value that is also forbidden is a fixture that can never pass,
        # and the failure would read as a model error rather than an authoring one.
        forbidden = {v for values in fixture.must_not_extract.values() for v in values}
        for field_name, value in fixture.expected.items():
            if isinstance(value, str) and value in forbidden:
                problems.contradictory_expectations.append(
                    f"{fixture.id}: {field_name} expects {value!r}, which must_not_extract forbids"
                )

    return problems


def main() -> int:
    fixtures = load_fixtures()
    problems = check_manifests(fixtures)

    by_capability: dict[str, int] = {}
    for fixture in fixtures:
        by_capability[fixture.capability] = by_capability.get(fixture.capability, 0) + 1

    print(f"corpus: {len(fixtures)} fixtures across {len(by_capability)} capabilities")
    for capability, count in sorted(by_capability.items()):
        high = sum(1 for f in fixtures if f.capability == capability and f.risk == "HIGH")
        print(f"  {capability:26s} {count:3d} fixtures  ({high} HIGH risk)")

    if not problems.ok:
        print("\nMANIFEST PROBLEMS")
        for label, items in (
            ("missing documents", problems.missing_documents),
            ("duplicate ids", problems.duplicate_ids),
            ("contradictory expectations", problems.contradictory_expectations),
            ("unknown risk level", problems.unknown_risk),
        ):
            for item in items:
                print(f"  {label}: {item}")
        print("\nGenerate the documents first: uv run python evals/fixtures/make_documents.py")
        return 1

    print("\nmanifests are coherent: every document exists, ids are unique, no")
    print("expectation contradicts a must_not_extract entry.")
    print()
    print("No capability runner is registered yet, so nothing was graded and no model")
    print("was called. Runners and deterministic graders land with the capabilities")
    print("they grade (AI_EVALUATION_PLAN.md §41 Phase 2) — writing a grader before the")
    print("thing it grades is a guess, and a harness that reports a score it did not")
    print("measure is the failure mode this project exists to avoid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
