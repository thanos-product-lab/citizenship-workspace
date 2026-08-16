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

# A currency this build does not recognise is treated as weaker than any it does. The
# alternative — skipping it — lets a group whose only non-current member is unrecognised
# report as CURRENT, describing it as assessed and up to date on the strength of a value
# the code could not interpret. That is the strongest-member reading ADR-0010 rejects,
# reached through a defensive branch.
_UNKNOWN_CURRENCY_WEAKNESS = max(_CURRENCY_WEAKNESS.values()) + 1


def _weakness(currency: str) -> int:
    return _CURRENCY_WEAKNESS.get(currency, _UNKNOWN_CURRENCY_WEAKNESS)


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
class ConclusionCount:
    conclusion: str
    count: int


@dataclass(frozen=True)
class GroupSummary:
    group_key: str
    #: Counts by conclusion, excluding NOT_YET_ASSESSED, **most severe first**. Ordered
    #: here rather than in the client: severity is a domain rule (RULES_SPEC §7.13), and a
    #: client sorting by magnitude would put the most reassuring state first on the screen
    #: a user most often reads only (CLAUDE.md §2.7).
    conclusion_counts: list[ConclusionCount] = field(default_factory=list)
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
    # An unrecognised conclusion is never silently counted as fine.
    return _severity_of(conclusion) >= _NEEDS_ATTENTION_FROM


def _severity_of(conclusion: str) -> int:
    try:
        return severity(Conclusion(conclusion))
    except ValueError:
        return 99  # unrecognised sorts first, toward visibility


def _ordered_counts(counts: Counter[str]) -> list[ConclusionCount]:
    return [
        ConclusionCount(conclusion=conclusion, count=count)
        for conclusion, count in sorted(
            counts.items(), key=lambda item: (-_severity_of(item[0]), item[0])
        )
    ]


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
        if weakest is None or _weakness(member.currency) > _weakness(weakest):
            weakest = member.currency

    return GroupSummary(
        group_key=group_key,
        conclusion_counts=_ordered_counts(counts),
        not_yet_assessed=unassessed,
        total=len(members),
        currency=weakest,
        needs_attention=attention,
        stale=stale,
    )


def total_conclusion_counts(summaries: Sequence[GroupSummary]) -> list[ConclusionCount]:
    """Case-wide counts, most severe first.

    Aggregated here rather than in the client: merging the per-group lists preserves each
    group's ordering but not the whole, so whichever conclusion the first group happened to
    hold would lead — in practice SUPPORTED, the most reassuring state, at the top of the
    screen a user most often reads only.
    """
    totals: Counter[str] = Counter()
    for summary in summaries:
        for entry in summary.conclusion_counts:
            totals[entry.conclusion] += entry.count
    return _ordered_counts(totals)


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
