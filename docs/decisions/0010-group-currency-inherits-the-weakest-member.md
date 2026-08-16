# ADR-0010: A requirement group's currency inherits its weakest member

**Status:** Accepted
**Date:** 2026-08-16
**Milestone:** M4 (slice 3)

## Context

ADR-0001 established that a result carries two independent axes — a conclusion (what we
concluded) and a currency (whether that conclusion is still current) — and that the UI
must render both and never collapse them. It was written about **one result**.

The case overview introduces requirement *group* summaries: six tiles, each compressing
between one and five results. Nothing in ADR-0001 says what a group's currency is when
one of its five members is stale, and the obvious implementations are wrong in a way
that is hard to see:

- A tile reading "Residence — 4 supported, 1 not currently satisfied" while
  `residence.total_absences` is STALE presents superseded arithmetic as current. It is
  precisely the failure ADR-0001 exists to prevent, one level up, where the reader has
  no per-result badge to correct the impression.
- The overview is the screen a user looks at *first* and often *only*. A compression that
  drops currency there does more damage than the same mistake on a detail page.

This was flagged during the M4 planning review as the finding the author was least sure
about, and left open until a rule could be chosen deliberately.

## Decision

A group's currency is the **weakest** currency among its members, ordered by distance from
"current":

```
CURRENT  <  PROVISIONAL  <  STALE  <  SUPERSEDED
```

One stale member makes the group stale. A group whose members all have no result at all
has a **null** currency, not `CURRENT` — reporting it as current would claim the group had
been assessed and found up to date.

Three supporting rules make the compression honest:

- **Conclusions are never merged.** The summary carries `conclusion_counts`, a tally by
  conclusion. There is deliberately no single "group state" enum: choosing one would mean
  choosing which member speaks for the group.
- **`NOT_YET_ASSESSED` is counted separately** and never appears in `conclusion_counts`.
  A stored placeholder result counts as unassessed too — having a row is not having a
  decision. `is_fully_concluded` is false whenever any member is unassessed, so a group
  cannot read as complete on the strength of requirements nothing has decided.
- **`stale` is a count, not just a flag**, so a client can say *how much* of a group is
  out of date rather than inferring it from one boolean.

## Alternatives rejected

- **A `has_stale` boolean beside the counts.** The original proposal. It carries the same
  information for the two-value case but cannot express `PROVISIONAL`, which the date
  simulator produces at M6 — the same reason ADR-0001 rejected a boolean `is_stale` for a
  single result. Rejecting it here for the same reason keeps the two levels consistent.
- **Refusing to summarise a group containing a stale member.** Honest, and briefly
  attractive: show nothing rather than something misleading. Rejected because it makes the
  overview *less* informative exactly when something needs attention — the user would lose
  the counts at the moment they matter most, and a blanked tile communicates less than a
  tile marked stale.
- **Strongest-member currency (a group is current if anything in it is).** Not seriously
  considered; recorded because it is the reading someone might reach for when a tile looks
  alarming. It is the false-reassurance direction CLAUDE.md §2.7 forbids.
- **Deriving group currency in the frontend from the requirement list.** The client already
  has every member's currency, so it could compute this. Rejected: it would put a domain
  rule in the browser and let two clients disagree about whether a group is stale.

## Consequences

- The overview can show a group's counts and its staleness without the two contradicting
  each other, and a stale member is visible from the first screen.
- `GroupSummary` is a projection type with no persistence; adding a currency value later
  means extending one ordered map (`_CURRENCY_WEAKNESS`) rather than revisiting callers.
- M6 introduces `PROVISIONAL` results from date simulation. The ordering above already
  places them, but the *presentation* of a provisional group is not yet designed and must
  be settled when the simulator lands.
- A future "case-level currency" (one badge for the whole case) would be this rule applied
  once more. It is deliberately **not** introduced here: the overview shows per-group
  currency and a case-level stale banner driven by counts, and collapsing the whole case
  into one currency badge would compress further than the evidence supports.

## Invariants touched

**CLAUDE.md §2.4 (conclusion and currency are separate).** This ADR extends it from a
single result to an aggregate. The two axes stay separate at group level: conclusions are
a tally, currency is its own field, and neither is derived from the other.

**CLAUDE.md §2.6 (no readiness score).** `conclusion_counts` is a tally of named
qualitative states, never a fraction, percentage, or ordered progress measure. `total` and
`not_yet_assessed` exist so a client can state what has *not* been assessed — increasing
visible uncertainty rather than manufacturing a completion figure. A client rendering
"4 of 5" from these fields would violate §2.6; the fields themselves do not.
