# ADR-0021: Evidence attaches to a travel record, ahead of and beside FactEvidenceLink

**Status:** Accepted
**Date:** 2026-08-25
**Milestone:** M7 (Evidence Foundation), slice 4a

## Context

M7 gave the product a document that is stored privately, processed asynchronously, and
read deterministically — and that influences nothing. Slice 5 (deletion, and what it
invalidates) has no meaning until something depends on a document, which is why coverage
precedes deletion.

The domain already anticipated the relationship. Domain §11.8 states that *"a travel record
may link to zero or more evidence items"* and that *"a travel record without evidence may
still be user-confirmed but must expose its support state"*. Neither invariant names a
table.

The one table that did exist on paper was `FactEvidenceLink` (Domain §22), and
DETERMINISTIC_RULES_SPEC §7.8 named it directly: a trip is unevidenced when it has no
`FactEvidenceLink`. That specification could not be implemented. `FactEvidenceLink` hangs
off `FactVersion`; facts extracted from documents are M8, gated behind claims, review
decisions, and a model call. Written that way, an M7 detection depended on an M8 entity for
no reason connected to what it measures — whether the user has attached a document to a
trip.

## Decision

**Add `EvidenceTravelLink` (Domain §11.9), attaching an evidence item directly to a travel
record, and reword §7.8's detection to "no available evidence link" so it abstracts over
link kinds rather than naming one.**

Two consequences of the wording, both intended:

1. `FactEvidenceLink` is not replaced or deferred. When M8 lands it joins the graph beside
   this table, and the rule keeps asking the same question of more edges.
2. Neither link kind is privileged. A trip evidenced by an M8 fact link is evidenced.

**The link points at the travel *record*, not the travel record *version*.** Editing a
trip's dates creates a new version (§11.8). What a booking evidences is the trip, not one
revision of its dates, so a version-scoped link would drop every attachment on every edit —
a user correcting a return date would find their evidence silently gone, and the
travel-consistency rule would report a newly unevidenced trip as though the user had
removed something.

This is the opposite choice to `FactEvidenceLink`, which links a fact version, and the
difference is not an inconsistency worth reconciling. A fact's *value* is the thing being
evidenced, so a changed value genuinely needs re-evidencing. A trip's identity survives a
date correction.

## Consequences

- `residence.travel_consistency` gains a v2.0.0 rule version declaring `EVIDENCE_SUPPORT` /
  `ALL_ACTIVE_EVIDENCE_LINKS`, and becomes the first rule to depend on something the user
  did not type. See ADR-0022 for what activating a second rule version costs.
- Domain §31.1 gains `EVIDENCE_LINK`, the only input-link kind that is not a version —
  because an evidence link has no version sequence, only `availability`. The full reasoning
  is in §31.1 itself.
- The evidence fan-out is deliberately **one** requirement. Attaching a document must not
  stale `residence.total_absences`: a user who deletes a booking has not changed how many
  days they were absent, only how well supported their account of it is. Tested in both
  directions.
- Slice 5's `mark_support_unavailable(...)` has one call site now and gains a second in M8.
  It is one function precisely so that M8 adds a line inside it rather than discovering a
  forgotten call site.
- A link is **not** a judgement that the document is the right document. Nothing in M7 reads
  a linked document's contents to decide whether it supports the trip. The rule answers "is
  this trip evidenced?" and nothing more; "is this the right evidence?" needs a model and is
  M8's question. Stating this is load-bearing — a support column that looked like
  verification would be false reassurance of exactly the kind directive 7 exists to prevent.

## Alternatives rejected

**Wait for `FactEvidenceLink` in M8.** Honest to the spec as written, and it would have left
slice 5 with nothing to invalidate — the deletion path, the most trust-sensitive code in the
milestone, shipped with no consumer and no test that deletion reaches a conclusion. It also
misreads what the spec was trying to say: §7.8 wanted "the user has not evidenced this
trip", and reached for the only link table that had been written down.

**Link the travel record version.** Rejected above: silent evidence loss on every date
correction.

**Attach trips to a document rather than documents to a trip.** The inverse relation is the
same table read the other way, but the *command* would be wrong. The user's sentence is
"this booking is for that trip", and the trip is what the rule reads and what the issue
queue names.

## Invariants touched

- **Directive 5 (no conclusion without provenance).** A rule now depends on evidence, so it
  must link the evidence it read; hence `EVIDENCE_LINK` in §31.1.
- **Directive 1 (AI output is a proposal, never a fact).** Untouched, and deliberately so:
  nothing here is model-proposed. A link is a user action, and the document it points at is
  untrusted material either way — the rule reads that the link exists, never what the
  document says.
