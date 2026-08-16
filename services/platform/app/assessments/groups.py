"""Summarising a requirement group without losing what the members said.

A group summary is a compression, and every compression can lie. The two it could tell
here are the ones this module exists to prevent:

- **Losing currency.** ADR-0001 says a result carries a conclusion *and* a currency and the
  UI must never collapse them. That was written about one result. A group tile reading
  "Residence — 4 supported" while one member is STALE presents superseded arithmetic as
  current at the aggregate level: the same failure, one level up, where it is easier to
  miss. So a group's currency **inherits the weakest** of its members (ADR-0010).
- **Absorbing the unassessed.** Six of the fifteen requirements have no evaluator yet.
  Folding them into a conclusion tally would let a group read as complete on the strength
  of requirements nothing has decided, so `not_yet_assessed` is counted separately and is
  never part of `conclusion_counts`.

There is deliberately no single "group state" enum. Picking one would mean choosing which
member speaks for the group, and the counts plus the weakest currency say more with less
invention.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.requirements.domain import Conclusion, Currency
from app.requirements.rules_core import severity

# Currency ordered by how far it is from "current", weakest last. A group inherits the
# highest rank present among its members (ADR-0010). SUPERSEDED is included for
# completeness but cannot occur here: group summaries read displayed results only, and a
# superseded result is by definition not displayed.
_CURRENCY_WEAKNESS: dict[str, int] = {
    Currency.CURRENT.value: 0,
    Currency.PROVISIONAL.value: 1,
    Currency.STALE.value: 2,
    Currency.SUPERSEDED.value: 3,
}


@dataclass(frozen=True)
class GroupMember:
    """One requirement's displayed state, flattened for summarising."""

    requirement_key: str
    group_key: str
    title: str
    conclusion: str
    currency: str | None
    display_order: int


@dataclass(frozen=True)
class GroupSummary:
    group_key: str
    #: Counts by conclusion, excluding NOT_YET_ASSESSED.
    conclusion_counts: dict[str, int] = field(default_factory=dict)
    #: Requirements in this group with no real conclusion yet — counted apart so a group
    #: containing them can never read as complete.
    not_yet_assessed: int = 0
    #: Total catalogued requirements in the group.
    total: int = 0
    #: The weakest currency among members that have one; null when none do.
    currency: str | None = None
    #: How many members need the user's attention (severity ≥ REQUIRES_JUDGEMENT).
    needs_attention: int = 0
    #: How many members are stale — named separately from `currency` so a client does not
    #: have to infer "how much of this is out of date" from a single flag.
    stale: int = 0

    @property
    def is_fully_concluded(self) -> bool:
        """Every catalogued requirement in the group has a real conclusion. Not the same as
        'all supported' — it only means nothing here is still unassessed."""
        return self.not_yet_assessed == 0 and self.total > 0


_NEEDS_ATTENTION_FROM = severity(Conclusion.REQUIRES_JUDGEMENT)


def _needs_attention(conclusion: str) -> bool:
    try:
        return severity(Conclusion(conclusion)) >= _NEEDS_ATTENTION_FROM
    except ValueError:
        # An unrecognised conclusion is never silently counted as fine.
        return True


def summarise_group(group_key: str, members: Sequence[GroupMember]) -> GroupSummary:
    counts: Counter[str] = Counter()
    unassessed = 0
    weakest: str | None = None
    attention = 0
    stale = 0

    for member in members:
        # A stored NOT_YET_ASSESSED result is a placeholder, not a decision. It counts as
        # unassessed regardless of whether a row exists for it.
        if member.conclusion == Conclusion.NOT_YET_ASSESSED.value:
            unassessed += 1
        else:
            counts[member.conclusion] += 1
            if _needs_attention(member.conclusion):
                attention += 1

        if member.currency is None:
            continue
        if member.currency == Currency.STALE.value:
            stale += 1
        rank = _CURRENCY_WEAKNESS.get(member.currency)
        if rank is None:
            continue
        if weakest is None or rank > _CURRENCY_WEAKNESS[weakest]:
            weakest = member.currency

    return GroupSummary(
        group_key=group_key,
        conclusion_counts=dict(counts),
        not_yet_assessed=unassessed,
        total=len(members),
        currency=weakest,
        needs_attention=attention,
        stale=stale,
    )


def summarise_groups(members: Sequence[GroupMember]) -> list[GroupSummary]:
    """One summary per group, in first-appearance order.

    Members arrive in the catalogue's display order, so groups come out in the order the
    catalogue intends — a group added to the catalogue lands in its intended position with
    no change here, and no hardcoded list of group keys to drift.
    """
    grouped: dict[str, list[GroupMember]] = {}
    for member in sorted(members, key=lambda m: m.display_order):
        grouped.setdefault(member.group_key, []).append(member)
    return [summarise_group(key, items) for key, items in grouped.items()]
