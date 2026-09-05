"""The claim→fact boundary: what cannot be done, and why it cannot.

Prime directive 1 is *"AI output is a proposal, never a fact"*. This file is the
assertion that the codebase makes the alternative unspellable rather than merely
unwritten — most of what is checked here is the **absence** of a capability, because an
absence is the only kind of guarantee that survives someone deleting a guard.
"""

import ast
import inspect
import pathlib
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.facts import service
from app.facts.domain import (
    HIGH_RISK_CLAIM_TYPES,
    SCHEMA_FOR_CLAIM_TYPE,
    ClaimReviewDecision,
    ClaimType,
    ExtractedClaim,
    FactVersion,
    ReviewDecision,
    ReviewMode,
)
from app.facts.values import (
    REVIEW_DERIVED,
    ProposedValue,
    ReviewedValue,
    SourceMethod,
    ValueSchema,
    normalise,
)
from app.shared.tenant import APP_ROLE

pytestmark = pytest.mark.integration


def _proposal(raw: str = "11 May 2026", iso: str | None = "2026-05-11") -> ProposedValue:
    return ProposedValue(schema=ValueSchema.DATE_V1, raw=raw, model_iso=iso)


def code_of(module_or_function: object) -> str:
    """A module's *executable* source, with docstrings and comments removed.

    Every structural guard in this milestone greps source for a name that must not
    appear, and three of them first failed on the module's own docstring explaining why
    that name must not appear. Prose that describes a rule is not a violation of it, and
    a check that cannot tell the two apart flags the very comment written to help the
    next reader — which teaches people to delete the explanation.
    """
    return _strip(ast.parse(inspect.getsource(module_or_function)))  # type: ignore[arg-type]


def _strip(tree: "ast.Module") -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    # `ast.unparse` drops comments as a side effect of round-tripping, which is the other
    # half of what this needs.
    return ast.unparse(tree)


def code_of_file(path: pathlib.Path) -> str:
    """`code_of` for a path rather than an imported object, so a scan can walk the whole
    package without importing every module in it."""
    return _strip(ast.parse(path.read_text()))


# --- layer 1: the type boundary -----------------------------------------------------


def test_there_is_no_way_to_build_a_fact_from_a_claim() -> None:
    """The single most important assertion in the milestone.

    `FactVersion` has exactly two constructors. One takes a `ReviewedValue`, which only
    a flushed `ClaimReviewDecision` can produce; the other takes a `UserEnteredValue`,
    which has no claim behind it. There is no third, and adding one is what this test
    exists to make impossible to do quietly.
    """
    constructors = sorted(
        name
        for name, _member in inspect.getmembers(FactVersion)
        if not name.startswith("__")
        and isinstance(inspect.getattr_static(FactVersion, name), classmethod)
    )
    assert constructors == ["from_review", "from_user_entry"], (
        f"FactVersion gained a constructor: {constructors}. Every route from a value to a "
        "trusted fact must pass through a recorded human decision."
    )


def test_from_review_accepts_only_a_reviewed_value() -> None:
    """A `ProposedValue` is not a `ReviewedValue` and nothing converts one to the other,
    so this is a `just typecheck` failure rather than a runtime check. Asserted on the
    signature, because a runtime test would only prove Python's tolerance."""
    signature = inspect.signature(FactVersion.from_review)
    first = next(iter(signature.parameters.values()))
    assert first.annotation is ReviewedValue


def test_nothing_converts_a_proposal_into_a_reviewed_value() -> None:
    """The other half. A constructor that took only `ReviewedValue` would be worthless
    if some helper manufactured one from a claim.

    **Scanned over the whole `app` package**, not over `values` and `domain` alone.
    `ReviewedValue` is a public frozen dataclass with a public constructor, so writing
    `ReviewedValue(decision_id=…, source_method=USER_CONFIRMED_AI_CLAIM, …)` in any
    module typechecks fine and `FactRepository.append_version` accepts it. The type
    boundary makes the *conversion* unspellable; only this makes the fabrication
    visible. Two files were the reviewable surface until the slice-3a trust review
    pointed out how much of the codebase they left out.

    The database is the real backstop — `ck_fact_versions_ai_requires_decision` refuses
    an AI-derived fact with no decision row whatever Python does. This is the layer that
    fails at review time instead of at insert time.
    """
    import app

    root = pathlib.Path(app.__file__).parent
    constructions = [
        f"{path.relative_to(root)}:{number}"
        for path in sorted(root.rglob("*.py"))
        for number, line in enumerate(code_of_file(path).splitlines(), start=1)
        if "ReviewedValue(" in line and not line.lstrip().startswith(("class ", "def "))
    ]
    assert len(constructions) == 1, (
        f"ReviewedValue is constructed in {len(constructions)} places: {constructions}. "
        "Only ClaimReviewDecision.outcome() may build one."
    )
    assert constructions[0].startswith("facts/domain.py:"), (
        f"the one construction moved to {constructions[0]}; it belongs in `outcome()`"
    )


def test_a_decision_must_be_durable_before_it_can_authorise_a_value(
    db_session: Session,
) -> None:
    """`outcome()` needs `self.id`, which SQLAlchemy assigns on flush. So a fact cannot
    reference a decision that is not yet in the database."""
    unflushed = ClaimReviewDecision(
        case_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        decision=ReviewDecision.CONFIRM.value,
        review_mode=ReviewMode.BLIND_ENTRY.value,
        corrected_raw="2026-05-11",
        corrected_normalised="2026-05-11",
        reviewed_by="user_a",
        reviewed_at=datetime.now(UTC),
    )
    # `id` is column-defaulted, so it is unset until the row is flushed. Read through
    # `getattr` because the mapped attribute is typed non-optional — true of a persisted
    # row and not of one that has never been written, which is the state under test.
    assert getattr(unflushed, "id", None) is None
    with pytest.raises(RuntimeError, match="flushed"):
        unflushed.outcome(schema=ValueSchema.DATE_V1)


def test_a_rejection_authorises_no_value() -> None:
    """RFC §10: reject creates no trusted fact. There is no `ReviewedValue` for a
    rejection to return, so a caller cannot obtain one by mistake."""
    rejected = ClaimReviewDecision(
        case_id=uuid.uuid4(),
        claim_id=uuid.uuid4(),
        decision=ReviewDecision.REJECT.value,
        review_mode=ReviewMode.PREFILLED.value,
        reason_code="VALUE_NOT_PRESENT",
        reviewed_by="user_a",
        reviewed_at=datetime.now(UTC),
    )
    object.__setattr__(rejected, "id", uuid.uuid4())
    with pytest.raises(ValueError, match="no trusted fact"):
        rejected.outcome(schema=ValueSchema.DATE_V1)


# --- layer 2: no parameter a claim could enter --------------------------------------


def test_the_assessment_inputs_have_no_field_a_claim_could_enter() -> None:
    """Plan §2 layer 2, still true now that claims exist.

    An unreviewed claim cannot influence a trusted assessment because there is nowhere
    in an evaluator's input to put one — the same argument that keeps simulated
    provenance out of `_persist_result`.
    """
    from app.requirements.evaluation import ResidenceAssessmentInputs, RouteAssessmentInputs

    for inputs in (RouteAssessmentInputs, ResidenceAssessmentInputs):
        annotations = {name: str(t) for name, t in inputs.__annotations__.items()}
        for name, annotation in annotations.items():
            for forbidden in ("ExtractedClaim", "ProposedValue", "ClaimView"):
                assert forbidden not in annotation, f"{inputs.__name__}.{name} accepts {forbidden}"


def test_no_trusted_query_reads_claims() -> None:
    """The assessment path reads `fact_versions` and the versioned residence tables. It
    does not read `extracted_claims`, and a query that did would be an unreviewed
    proposal reaching a conclusion."""
    from app.assessments import invalidation
    from app.assessments import service as assessments
    from app.requirements import evaluation

    # Three modules, not one. The first version of this test scanned
    # `assessments.service` alone, which is where `evaluate_case` lives — but the
    # evaluators and the stale-propagation path are equally trusted readers, and an
    # evaluator reading `extracted_claims` is precisely the failure this test is named
    # for. Caught by the slice-3a trust review.
    for module in (assessments, evaluation, invalidation):
        source = code_of(module)
        assert "ExtractedClaim" not in source, f"{module.__name__} names a claim type"
        assert "extracted_claims" not in source, f"{module.__name__} queries claims"


def test_the_extractor_cannot_name_a_fact_type() -> None:
    """The module that creates claims must not be able to create facts. Structural,
    because a behavioural test only covers the paths it happens to exercise."""
    from app.ai import extraction_service

    source = code_of(extraction_service)
    for forbidden in (
        "FactVersion",
        "CaseFact",
        "FactEvidenceLink",
        "ClaimReviewDecision",
        # The two the first version of this list missed, and the gap was real: the
        # extractor could have built a `ReviewedValue` by hand and handed it to
        # `append_version` without naming any of the four names above. Named directly
        # by the slice-3a trust review.
        "ReviewedValue",
        "FactRepository",
    ):
        assert forbidden not in source, f"the extractor names {forbidden} in code"


# --- layer 3: the database ----------------------------------------------------------


def test_an_ai_derived_fact_cannot_exist_without_a_decision(db_session: Session) -> None:
    """The CHECK that carries prime directive 1 in SQL. Defence in depth behind the type
    boundary, and the half that survives someone reaching for the ORM."""
    from sqlalchemy.exc import IntegrityError

    definition = str(
        db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_fact_versions_ai_requires_decision'"
            )
        ).scalar_one()
    )
    for method in REVIEW_DERIVED:
        assert method.value in definition

    # Run with the tenant cleared, as the table owner. Under RLS the policy refuses this
    # insert first — correctly, and for a different reason than the one under test. The
    # CHECK is the guarantee that survives a caller who *is* the owner.
    from app.shared.tenant import clear_tenant, set_tenant

    clear_tenant(db_session)
    fact_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        db_session.execute(
            text(
                "INSERT INTO fact_versions (id, case_fact_id, version_number, "
                "value_schema_version, raw_value, source_method, created_by) "
                "VALUES (gen_random_uuid(), :f, 1, 'date.v1', 'x', "
                "'USER_CONFIRMED_AI_CLAIM', 'user_a')"
            ),
            {"f": fact_id},
        )
    db_session.rollback()
    set_tenant(db_session, "user_a")


def test_the_review_derived_set_agrees_with_the_constraint(db_session: Session) -> None:
    """`REVIEW_DERIVED` in Python and the CHECK in migration 0030 say the same thing in
    two languages. Drift would let a source method claim a review it never had."""
    definition = str(
        db_session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_fact_versions_ai_requires_decision'"
            )
        ).scalar_one()
    )
    import re

    in_sql = set(re.findall(r"'([A-Z_]+)'::character varying", definition))
    assert in_sql == {m.value for m in REVIEW_DERIVED}


# --- the value model ----------------------------------------------------------------


def test_every_claim_type_has_a_value_schema() -> None:
    """A claim type with no schema could be created with any shape at all, which is the
    one thing `value_schema_version` exists to prevent."""
    assert set(SCHEMA_FOR_CLAIM_TYPE) == set(ClaimType)


def test_the_high_risk_set_is_exactly_the_date_fields() -> None:
    """RFC §41.3. Derived rather than listed, so a date field added later is high-risk
    the moment it exists — a hand-kept copy is a list somebody forgets, and what it
    gates is blind confirmation and the bulk-confirm ban."""
    dates = {t for t, s in SCHEMA_FOR_CLAIM_TYPE.items() if s is ValueSchema.DATE_V1}
    assert dates == HIGH_RISK_CLAIM_TYPES
    assert ClaimType.TRAVEL_DEPARTURE_DATE in HIGH_RISK_CLAIM_TYPES
    assert ClaimType.TRAVEL_BOOKING_REFERENCE not in HIGH_RISK_CLAIM_TYPES


def test_the_normaliser_ignores_what_the_model_said() -> None:
    """The spike's central finding, as an assertion (AI_SPIKE_FINDINGS §3.1).

    The model's `iso` is present and confident and the written form is ambiguous, so the
    normaliser returns None. If it ever consulted `model_iso`, a behaviour that swung
    from 0/3 to 3/3 on prompt wording would be deciding a date on a high-risk field.
    """
    ambiguous = ProposedValue(schema=ValueSchema.DATE_V1, raw="03/04/2025", model_iso="2025-04-03")
    assert normalise(ambiguous) is None

    unambiguous = ProposedValue(
        schema=ValueSchema.DATE_V1, raw="11 May 2026", model_iso="2018-01-01"
    )
    assert normalise(unambiguous) == "2026-05-11", "the model's wrong iso was used"


def test_a_claim_cannot_be_born_confirmed() -> None:
    """`propose()` is the only constructor and there is no argument by which a claim can
    arrive already decided about."""
    claim = ExtractedClaim.propose(
        case_id=uuid.uuid4(),
        evidence_item_id=uuid.uuid4(),
        evidence_file_id=uuid.uuid4(),
        extraction_run_id=uuid.uuid4(),
        claim_type=ClaimType.TRAVEL_DEPARTURE_DATE,
        value=_proposal(),
    )
    assert claim.status == "PENDING_REVIEW"
    assert "status" not in inspect.signature(ExtractedClaim.propose).parameters


def test_a_claim_rejects_a_value_of_the_wrong_shape() -> None:
    with pytest.raises(ValueError, match=r"date\.v1"):
        ExtractedClaim.propose(
            case_id=uuid.uuid4(),
            evidence_item_id=uuid.uuid4(),
            evidence_file_id=uuid.uuid4(),
            extraction_run_id=uuid.uuid4(),
            claim_type=ClaimType.TRAVEL_DEPARTURE_DATE,
            value=ProposedValue(schema=ValueSchema.TEXT_V1, raw="Gatwick"),
        )


def test_source_method_has_no_ai_only_value() -> None:
    """RFC §11: *"AI alone is never a trusted source method."* Both AI-derived values
    name a human, and there is no third that does not."""
    ai_ish = [m for m in SourceMethod if "AI" in m.value and "USER" not in m.value]
    assert ai_ish == []


# --- no bulk confirm ----------------------------------------------------------------


def test_there_is_no_bulk_review_endpoint() -> None:
    """MVP §8.11 forbids bulk confirmation for high-risk date fields. Met by there being
    no batch route at all — a route that does not exist cannot be called with a date
    claim, and cannot acquire a special case later without someone writing it."""
    from app.main import app

    paths = list(app.openapi()["paths"])
    for path in paths:
        assert "review-all" not in path
        assert "bulk" not in path
    review_routes = [p for p in paths if p.endswith("/review")]
    assert review_routes == ["/api/v1/cases/{case_id}/claims/{claim_id}/review"], (
        f"more than one review route exists: {review_routes}"
    )


def test_the_review_service_takes_one_claim() -> None:
    """The other half of the same guarantee: even without a route, a service accepting a
    list would be one FastAPI decorator away from a bulk endpoint."""
    parameters = inspect.signature(service.review).parameters
    assert "claim_id" in parameters
    assert "claim_ids" not in parameters
    assert str(parameters["claim_id"].annotation) in ("<class 'uuid.UUID'>", "uuid.UUID")


def test_a_model_guess_on_an_ambiguous_date_reaches_nothing(db_session: Session) -> None:
    """Observed in the shipped system, not argued from the spike.

    Running `just eval --run` against the real model on 2026-09-05, the travel extractor
    abstained on `03/04/2025` and **guessed** `2025-04-09` for `09/04/2025` in the same
    document. Nothing in that document settles the convention — neither date has a
    component above 12 — so the second answer was a guess the prompt explicitly forbids.

    The eval gate fails on it, correctly: the model did the thing we said it must not.
    The *product* is unharmed, and this test is why. `normalise` ignores `model_iso`
    entirely, so the claim reaches review with no deterministic reading and a person is
    asked what the document means.

    That is the whole argument for putting the normaliser in Python rather than trusting
    the prompt (AI_SPIKE_FINDINGS §3.1), demonstrated rather than predicted. If this
    test ever fails, a model's guess is deciding a high-risk date.
    """
    guessed = ExtractedClaim.propose(
        case_id=uuid.uuid4(),
        evidence_item_id=uuid.uuid4(),
        evidence_file_id=uuid.uuid4(),
        extraction_run_id=uuid.uuid4(),
        claim_type=ClaimType.TRAVEL_RETURN_DATE,
        value=ProposedValue(schema=ValueSchema.DATE_V1, raw="09/04/2025", model_iso="2025-04-09"),
    )

    assert guessed.proposed_iso == "2025-04-09", "the guess is kept, for the record"
    assert guessed.normalised_value is None, (
        "a model guess on an ambiguous date became the system's reading of it"
    )
    assert guessed.is_high_risk, "so it is confirmed blind, by a person reading the page"


# --- what the database refuses, independently of the code -----------------------------


def _table_update(session: Session, table: str) -> bool:
    return bool(
        session.execute(
            text("SELECT has_table_privilege(:role, :table, 'UPDATE')"),
            {"role": APP_ROLE, "table": table},
        ).scalar_one()
    )


def _column_update(session: Session, table: str, column: str) -> bool:
    return bool(
        session.execute(
            text("SELECT has_column_privilege(:role, :table, :column, 'UPDATE')"),
            {"role": APP_ROLE, "table": table, "column": column},
        ).scalar_one()
    )


@pytest.mark.integration
@pytest.mark.parametrize("table", ["claim_review_decisions", "fact_versions"])
def test_the_request_role_cannot_rewrite_a_record_of_what_happened(
    db_session: Session, table: str
) -> None:
    """Migration 0032.

    `claim_review_decisions` is the row that separates a proposal from a decision, and
    `fact_versions` is the value a historical assessment resolves to. Everything above
    in this file is a guarantee in Python; this is the same guarantee in the one place
    that holds when the Python is wrong.

    Column-level too, not just table-level: `has_table_privilege` returns false when the
    role holds UPDATE on *some* columns, so a table check alone would pass a grant that
    left a single column writable.
    """
    assert not _table_update(db_session, table)
    columns = [
        row[0]
        for row in db_session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :table"),
            {"table": table},
        )
    ]
    writable = [c for c in columns if _column_update(db_session, table, c)]
    assert writable == [], f"{APP_ROLE} can rewrite {writable} on {table}"


@pytest.mark.integration
def test_a_claim_is_redactable_but_not_rewritable(db_session: Session) -> None:
    """The rule the column grant states, which neither a blanket grant nor a blanket
    revoke can say.

    Deletion is obliged to erase the document's own words out of `proposed_raw`, so the
    request role must be able to write it — the purge runs as `app_rls` like every other
    case-scoped write. What it must never be able to write is which run read which field
    of which document, and how sure the model said it was: that is what the claim *is*,
    and rewriting it would let a proposal be re-attributed after the fact.
    """
    identity = (
        "case_id",
        "evidence_item_id",
        "evidence_file_id",
        "extraction_run_id",
        "claim_type",
        "journey_index",
        "value_schema_version",
        "model_confidence",
        "created_at",
    )
    writable = [c for c in identity if _column_update(db_session, "extracted_claims", c)]
    assert writable == [], f"a claim's identity is rewritable: {writable}"

    # And the two things that legitimately change: its status, and its content when the
    # document behind it is destroyed.
    assert _column_update(db_session, "extracted_claims", "status")
    assert _column_update(db_session, "extracted_claims", "proposed_raw")
