"""Every code a rule can emit must render, and every template must be reachable.

The important test here is `test_no_rule_code_is_missing_a_template`. It scans the rules
modules for code literals rather than checking a hand-written list, because a hand-written
list is exactly the thing that goes stale when someone adds a band: the rule would ship,
the API would return `text: null`, and the UI would silently fall back to showing a bare
`TOTAL_ABSENCES_SOMETHING_NEW` to a user. The scan makes that a red test instead.
"""

import re
from pathlib import Path

import pytest

from app.assessments.invalidation import StaleReason
from app.requirements import messages, route_rules
from app.requirements.messages import (
    ISSUE_TITLE_TEMPLATES,
    LIMITATION_TEMPLATES,
    NEXT_ACTION_TEMPLATES,
    STALE_REASON_TEMPLATES,
    SUMMARY_TEMPLATES,
    format_date,
    render_limitation,
    render_next_action,
    render_stale_reason,
    render_summary,
)
from app.requirements.rules_core import (
    PRESENCE_SEARCH_HORIZON_DAYS,
    band_final_year_absences,
    band_total_absences,
)

_RULES_MODULES = ("evaluation.py", "route_rules.py", "rules_core.py")

# SCREAMING_CASE literals in the rules modules that are *not* user-facing codes: enum
# member values and raw domain strings. Anything else the scan finds must have a
# template — including, deliberately, a newly added value, which fails here until it is
# classified as one or the other.
_NOT_MESSAGE_CODES = frozenset(
    {
        # LinkInputKind
        "ROUTE_PROFILE_VERSION",
        "APPLICATION_DATE_VERSION",
        "TRAVEL_RECORD_VERSION",
        # ContributionRole
        "REQUIRED",
        "SUPPORTING",
        "CONTRADICTING",
        "LIMITING",
        "CONTEXTUAL",
        # LimitationSeverity
        "INFORMATION",
        "CAUTION",
        "REVIEW_REQUIRED",
        "BLOCKING",
        # DateConfidence, compared as raw strings so the rules import no other module
        "EXACT",
        "ESTIMATED",
        "UNKNOWN",
        "CONFLICTING",
        # StatusType, likewise
        "EU_SETTLED_STATUS",
    }
)


def _all_templated_codes() -> set[str]:
    return (
        set(SUMMARY_TEMPLATES)
        | set(LIMITATION_TEMPLATES)
        | set(NEXT_ACTION_TEMPLATES)
        | set(STALE_REASON_TEMPLATES)
    )


def _scanned_codes() -> set[str]:
    rules_dir = Path(messages.__file__).parent
    found: set[str] = set()
    for name in _RULES_MODULES:
        source = (rules_dir / name).read_text()
        found |= set(re.findall(r"""["']([A-Z][A-Z0-9_]{4,})["']""", source))
    return found - _NOT_MESSAGE_CODES


def test_no_rule_code_is_missing_a_template() -> None:
    missing = _scanned_codes() - _all_templated_codes()
    assert not missing, (
        f"these codes are emitted by a rule but have no template: {sorted(missing)}. "
        "Add one in app/requirements/messages.py, or add the value to _NOT_MESSAGE_CODES "
        "if it is an enum member rather than a user-facing code."
    )


def test_every_band_summary_code_has_a_template() -> None:
    """Derived from the band tables themselves, so a new band cannot slip through even if
    the source scan's regex were to miss it."""
    for days in range(0, 1000):
        assert band_total_absences(days).summary_code in SUMMARY_TEMPLATES
        assert band_final_year_absences(days).summary_code in SUMMARY_TEMPLATES


def test_every_route_rule_summary_code_has_a_template() -> None:
    """route_rules declares its codes as module constants whose value equals their name."""
    codes = {
        value
        for name, value in vars(route_rules).items()
        if name.isupper() and isinstance(value, str) and value == name
    }
    assert codes, "expected route_rules to declare summary-code constants"
    assert codes <= set(SUMMARY_TEMPLATES)


def test_every_stale_reason_has_a_template() -> None:
    codes = {
        value
        for name, value in vars(StaleReason).items()
        if not name.startswith("_") and isinstance(value, str)
    }
    assert codes == set(STALE_REASON_TEMPLATES)


@pytest.mark.parametrize("code", sorted(SUMMARY_TEMPLATES))
def test_every_summary_renders_without_its_parameters(code: str) -> None:
    """A template must not raise on a missing parameter. A read endpoint that 500s because
    a rule omitted an optional parameter is a worse failure than a vaguer sentence."""
    text = render_summary(code, {})
    assert text and text.strip()


@pytest.mark.parametrize("code", sorted(LIMITATION_TEMPLATES))
def test_every_limitation_renders_without_its_parameters(code: str) -> None:
    text = render_limitation(code, {})
    assert text and text.strip()


def test_unknown_code_renders_as_none_not_as_prose() -> None:
    """An unrecognised code must not be guessed at. None lets the caller fall back to the
    structured fields; an invented sentence would be the product asserting something no
    rule concluded."""
    assert render_summary("NOT_A_REAL_CODE", {}) is None
    assert render_limitation("NOT_A_REAL_CODE", {}) is None
    assert render_next_action("NOT_A_REAL_CODE", {}) is None
    assert render_stale_reason("NOT_A_REAL_CODE", {}) is None
    assert render_summary(None) is None


# --- the two copy rules the module docstring commits to ----------------------


def test_absence_summary_names_the_figure_as_confirmed() -> None:
    """CLAUDE.md §2.1: an unconfirmed record's days must never read as established fact,
    so the sentence says which records the figure counts."""
    text = render_summary(
        "TOTAL_ABSENCES_NEAR_THRESHOLD",
        {"days": 439, "provisional_days": 439, "threshold": 450, "trip_count": 12},
    )
    assert text is not None
    assert "439 days" in text
    assert "confirmed travel records" in text
    assert "threshold of 450" in text


def test_absence_summary_never_frames_the_gap_as_headroom() -> None:
    """ "11 days remaining" would be advice, and would invite treating NEAR_THRESHOLD as a
    pass with room to spare. The difference must not appear at all."""
    text = render_summary(
        "TOTAL_ABSENCES_NEAR_THRESHOLD",
        {"days": 439, "provisional_days": 439, "threshold": 450, "trip_count": 12},
    )
    assert text is not None
    assert "11" not in text
    assert "remaining" not in text.lower()
    assert "left" not in text.lower()


def test_the_verdict_follows_the_provisional_figure_when_the_two_diverge() -> None:
    """The §6.2 sensitivity rule can give a result the *provisional* band's summary code
    without capping it: trusted 400 bands SUPPORTED, provisional 440 bands NEAR_THRESHOLD.
    Attaching "that is close to the standard threshold" to the figure 400 would describe
    400 as near 450, which it is not. The verdict must sit with the figure it describes."""
    text = render_summary(
        "TOTAL_ABSENCES_NEAR_THRESHOLD",
        {"days": 400, "provisional_days": 440, "threshold": 450},
    )
    assert text is not None
    assert "Including those, that is close to the standard threshold." in text
    assert "confirmed travel records, against a threshold of 450. That is close" not in text
    assert text.index("400") < text.index("440") < text.index("close to the standard")


def test_the_capped_codes_keep_their_own_wording_about_both_figures() -> None:
    """The two UNCONFIRMED_REVIEW verdicts already speak about confirmed *and*
    unconfirmed records, so they must not be re-prefixed with "Including those,"."""
    text = render_summary(
        "TOTAL_ABSENCES_UNCONFIRMED_REVIEW",
        {"days": 439, "provisional_days": 470, "threshold": 450},
    )
    assert text is not None
    assert "Including those," not in text
    assert "cannot be settled yet" in text


def test_an_absence_summary_without_a_figure_asserts_no_verdict() -> None:
    """A missing `days` parameter must not leave a threshold verdict standing with no
    number behind it — "None days ... That is within the standard threshold" would be the
    product asserting an outcome it cannot support."""
    text = render_summary("TOTAL_ABSENCES_WITHIN_THRESHOLD", {"threshold": 450})
    assert text is not None
    assert "within the standard threshold" not in text
    assert "None" not in text
    assert "not available" in text


def test_the_presence_horizon_is_not_restated_in_copy() -> None:
    """The sentence must track `PRESENCE_SEARCH_HORIZON_DAYS` rather than repeating 90,
    so changing the constant cannot leave the copy asserting something false."""
    text = render_summary("PRESENCE_NOT_SUPPORTED", {"physical_presence_date": "2022-04-16"})
    assert text is not None
    assert f"next {PRESENCE_SEARCH_HORIZON_DAYS} days" in text


def test_divergent_figures_are_stated_separately() -> None:
    """The §5.3 risk: `days` and `provisional_days` are equal in the canonical case, so a
    template that quietly rendered the provisional figure would look correct everywhere.
    When they differ, the sentence must give the confirmed figure first and name the rest
    as unconfirmed."""
    text = render_summary(
        "TOTAL_ABSENCES_NEAR_THRESHOLD",
        {"days": 439, "provisional_days": 452, "threshold": 450, "trip_count": 13},
    )
    assert text is not None
    assert "439 days" in text
    assert "have not confirmed" in text
    assert "13 days" in text  # the excess, named as unconfirmed
    assert "452" in text
    # The confirmed figure leads; the provisional one never stands alone.
    assert text.index("439") < text.index("452")


def test_identical_figures_add_no_unconfirmed_clause() -> None:
    text = render_summary(
        "TOTAL_ABSENCES_NEAR_THRESHOLD",
        {"days": 439, "provisional_days": 439, "threshold": 450},
    )
    assert text is not None
    assert "have not confirmed" not in text


def test_presence_not_supported_states_the_resolving_date_only_when_there_is_one() -> None:
    with_date = render_summary(
        "PRESENCE_NOT_SUPPORTED",
        {"physical_presence_date": "2022-04-16", "resolving_application_date": "2027-04-25"},
    )
    assert with_date is not None
    assert "16 April 2022" in with_date
    assert "25 April 2027" in with_date

    without_date = render_summary(
        "PRESENCE_NOT_SUPPORTED", {"physical_presence_date": "2022-04-16"}
    )
    assert without_date is not None
    assert "No later date" in without_date


def test_unconfirmed_limitation_handles_both_parameter_shapes() -> None:
    """One code, two raising rules: the absence rules pass day counts, physical presence
    passes the anchor date. Neither shape may fall through to the generic sentence."""
    from_absences = render_limitation(
        "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION",
        {"trusted_days": 439, "provisional_days": 452},
    )
    assert from_absences is not None
    assert "439" in from_absences and "452" in from_absences

    from_presence = render_limitation(
        "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION", {"physical_presence_date": "2022-04-16"}
    )
    assert from_presence is not None
    assert "16 April 2022" in from_presence


# --- date formatting --------------------------------------------------------


@pytest.mark.parametrize(
    ("iso", "expected"),
    [
        ("2027-04-15", "15 April 2027"),
        ("2022-04-16", "16 April 2022"),
        ("2024-02-29", "29 February 2024"),
        ("2027-01-01", "1 January 2027"),
        ("2027-12-31", "31 December 2027"),
    ],
)
def test_format_date(iso: str, expected: str) -> None:
    assert format_date(iso) == expected


def test_format_date_passes_through_an_unparseable_value() -> None:
    assert format_date("not a date") == "not a date"
    assert format_date(None) == "None"


def test_day_pluralisation() -> None:
    one = render_summary("TOTAL_ABSENCES_WITHIN_THRESHOLD", {"days": 1, "threshold": 450})
    assert one is not None and "1 day outside" in one
    two = render_summary("TOTAL_ABSENCES_WITHIN_THRESHOLD", {"days": 2, "threshold": 450})
    assert two is not None and "2 days outside" in two


def test_every_issue_title_code_has_all_three_templates() -> None:
    """A queue item is a heading, a body and a "why it matters" line. A code with only
    some of them renders a card that trails off, and the omission is invisible until
    someone opens the destination with that issue type live."""
    from app.requirements.messages import (
        ISSUE_BODY_TEMPLATES,
        ISSUE_IMPACT_TEMPLATES,
        ISSUE_TITLE_TEMPLATES,
    )

    assert set(ISSUE_TITLE_TEMPLATES) == set(ISSUE_BODY_TEMPLATES) == set(ISSUE_IMPACT_TEMPLATES)


def test_every_derived_issue_has_its_templates() -> None:
    """The codes the derivation can emit, against the codes the copy defines. This is the
    drift that produces a card titled `ISSUE_OVERLAPPING_TRAVEL` on a user's screen."""
    import ast
    import pathlib

    from app.requirements.messages import ISSUE_TITLE_TEMPLATES

    source = pathlib.Path("app/issues/derivation.py").read_text()
    emitted: set[str] = {
        node.value.value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.keyword)
        and node.arg == "title_code"
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    # The conditional expression for the in/out-of-window uncertain codes is not a bare
    # constant keyword, so pick those up too.
    emitted |= {
        value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Constant)
        and isinstance(value := node.value, str)
        and value.startswith("ISSUE_")
    }
    assert emitted, "expected derivation.py to name at least one title code"
    assert emitted <= set(ISSUE_TITLE_TEMPLATES), sorted(emitted - set(ISSUE_TITLE_TEMPLATES))


@pytest.mark.parametrize("code", sorted(ISSUE_TITLE_TEMPLATES))
def test_every_issue_template_renders_without_its_parameters(code: str) -> None:
    from app.requirements.messages import (
        render_issue_body,
        render_issue_impact,
        render_issue_title,
    )

    assert render_issue_title(code, {})
    assert render_issue_body(code, {})
    assert render_issue_impact(code, {})
