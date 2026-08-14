"""Deriving the case phase (Domain §7.5).

The phase is a **user-facing projection**, not stored state: "derived from case state,
assessments, and issues". The `cases.current_phase` column predates the requirements
engine — it is written once at case creation and never advanced by anything, so a fully
assessed case still reports `SETTING_UP`. Nothing may read that column to answer "what
phase is this case in"; this module answers it instead. ADR-0009 records the rule.

`derive_phase` is a pure function of primitives: the caller gathers the case's current
requirement states and passes them in. It reads no session and no clock, so the whole
ladder is testable as a table.

Two phases are deliberately unreachable at M4. `FINAL_REVIEW` depends on evidence and
issue state that does not exist yet, and `NEARLY_PREPARED` requires every catalogued
requirement to have a real conclusion — six of the fifteen have no evaluator until M6/M7.
Reporting either early would tell a user their case is further along than it is, which is
the failure mode this product exists to avoid (CLAUDE.md §2.7). They stay in the ladder,
covered by unit tests over synthetic states, and simply do not occur in a real M4 case.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.cases.domain import CasePhase, LifecycleStatus
from app.requirements.domain import Conclusion, Currency
from app.requirements.rules_core import severity

# A conclusion at or above this severity is something the user has to deal with, so the
# case reads as RESOLVING_ISSUES. This is the boundary between "worth knowing" and
# "needs you": NEAR_THRESHOLD is a caution and does not move the phase; REQUIRES_JUDGEMENT
# and everything more severe does. Defined against `rules_core.severity` so the ordering
# has one owner (RULES_SPEC §7.13) and this module never re-ranks conclusions.
_NEEDS_ATTENTION_FROM = severity(Conclusion.REQUIRES_JUDGEMENT)


@dataclass(frozen=True)
class RequirementState:
    """One requirement's displayed result, flattened. `conclusion` and `currency` stay
    separate here exactly as they are on the result (ADR-0001) — the phase reads both."""

    conclusion: str
    currency: str

    @property
    def is_concluded(self) -> bool:
        """A stored NOT_YET_ASSESSED result (e.g. the adult rule with no date of birth
        yet) is a placeholder, not a conclusion. It must not count towards completeness,
        or a case would read as prepared on the strength of requirements nothing decided."""
        return self.conclusion != Conclusion.NOT_YET_ASSESSED.value

    @property
    def needs_attention(self) -> bool:
        try:
            return severity(Conclusion(self.conclusion)) >= _NEEDS_ATTENTION_FROM
        except ValueError:  # an unrecognised conclusion is not silently treated as fine
            return True

    @property
    def is_stale(self) -> bool:
        return self.currency == Currency.STALE.value


def derive_phase(
    *,
    lifecycle_status: LifecycleStatus,
    states: Sequence[RequirementState],
    catalogue_size: int,
) -> CasePhase:
    """The case's phase, derived. `states` holds one entry per requirement that has a
    displayed (non-superseded) result; `catalogue_size` is the number of catalogued
    requirements, so requirements with no result at all are `catalogue_size - len(states)`.

    Order matters: a case with both an unmet requirement and unassessed ones is resolving
    issues, not building — the problem is the more useful thing to say.
    """
    if lifecycle_status is not LifecycleStatus.ACTIVE:
        # Onboarding, or a terminal state where the phase is not meaningful and the UI
        # shows a lifecycle notice instead.
        return CasePhase.SETTING_UP

    if not states:
        return CasePhase.SETTING_UP

    if any(state.is_stale or state.needs_attention for state in states):
        return CasePhase.RESOLVING_ISSUES

    if sum(1 for state in states if state.is_concluded) < catalogue_size:
        return CasePhase.BUILDING_CASE

    return CasePhase.NEARLY_PREPARED
