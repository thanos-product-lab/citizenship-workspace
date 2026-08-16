"""Choosing the three actions the overview shows.

UI/UX §6.4 caps the overview at three high-priority actions. That cap is a promise about
attention, not about completeness — so the selection has to be deterministic, explainable,
and honest about what it left out.

**Ordering** (first key wins, all descending in urgency):

1. `blocking` — an action without which the requirement cannot be satisfied.
2. the severity of the conclusion that raised it (RULES_SPEC §7.13, via `rules_core`), so
   an action from NOT_CURRENTLY_SATISFIED outranks one from NEAR_THRESHOLD.
3. the action's own `priority`, as the rule set it.
4. the requirement's `display_order`, so ties resolve the way the catalogue is ordered
   rather than by dict iteration.

**Two actions with the same code are not duplicates.** Physical presence may propose
2027-04-25 while the holding-period rule proposes its own earliest date; both are
`SELECT_APPLICATION_DATE`. Merging them into one "change your application date" would
invent a date neither rule produced, and dropping one would hide a real constraint. They
are deduplicated only on **code *and* parameters** — genuinely identical asks.

`total` is reported alongside the capped list so the UI can say how many were not shown.
A cap that silently hides work is a cap that misleads.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.requirements.domain import Conclusion, Currency
from app.requirements.rules_core import severity


@dataclass(frozen=True)
class CandidateAction:
    """A next action from one result, with the context needed to rank it."""

    requirement_key: str
    requirement_title: str
    conclusion: str
    #: The currency of the result that raised this action. Displayed results include STALE
    #: (`_SUPERSEDABLE`), so an action can be derived from arithmetic the system has itself
    #: flagged as not rechecked. Presenting that as a current instruction — with a blocking
    #: claim attached — is ADR-0001's failure applied to actions, and unlike a group tile
    #: there is no second badge to correct it. The card must be able to say so.
    currency: str | None
    display_order: int
    code: str
    parameters: dict[str, Any]
    priority: int
    blocking: bool


@dataclass(frozen=True)
class PriorityActions:
    shown: list[CandidateAction]
    #: How many distinct actions exist in total, so the UI can say what it is not showing.
    total: int

    @property
    def hidden(self) -> int:
        return max(0, self.total - len(self.shown))


MAX_SHOWN = 3


def _conclusion_severity(conclusion: str) -> int:
    try:
        return severity(Conclusion(conclusion))
    except ValueError:
        # An unrecognised conclusion sorts as most urgent rather than least: an action we
        # cannot rank should surface for a human, not sink out of view.
        return 99


def _sort_key(action: CandidateAction) -> tuple[int, int, int, int, int]:
    return (
        0 if action.blocking else 1,
        -_conclusion_severity(action.conclusion),
        # A current result outranks a stale one raising the same ask: acting on rechecked
        # arithmetic is strictly better advice.
        0 if action.currency == Currency.CURRENT.value else 1,
        action.priority,
        action.display_order,
    )


def _identity(action: CandidateAction) -> tuple[str, str]:
    # Code *and* parameters. Two SELECT_APPLICATION_DATE actions proposing different dates
    # are two different constraints and must both survive.
    return (action.code, repr(sorted(action.parameters.items())))


def select_priority_actions(
    candidates: Sequence[CandidateAction], *, limit: int = MAX_SHOWN
) -> PriorityActions:
    # Sort **before** deduplicating. Deduplicating first would keep whichever identical ask
    # came earliest in catalogue order, which may be the non-blocking, less severe one —
    # the card would then link to the weaker requirement and drop its blocking flag while
    # the stronger constraint disappeared and `hidden` counted it as shown.
    ordered = sorted(candidates, key=_sort_key)

    seen: set[tuple[str, str]] = set()
    distinct: list[CandidateAction] = []
    for action in ordered:
        identity = _identity(action)
        if identity in seen:
            continue
        seen.add(identity)
        distinct.append(action)

    return PriorityActions(shown=distinct[:limit], total=len(distinct))
