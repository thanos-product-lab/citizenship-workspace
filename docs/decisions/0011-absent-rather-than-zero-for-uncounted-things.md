# ADR-0011: A field is absent, not zero, until something counts it

**Status:** Accepted
**Date:** 2026-08-16
**Milestone:** M4 (slice 3)

## Context

Domain Model RFC §44.1 specifies `CaseOverviewProjection` as including an **open issue
count** and an **evidence coverage** summary. Neither subsystem exists at M4: issue
detection arrives at M6, evidence at M5.

The obvious implementation is to return `0` and `0%` until they do. On a screen headed
"What to do next", beside a line claiming where "most of the outstanding work" is, a zero
does not read as "not implemented" — it reads as **the system looked and found none**.
That is a stronger claim than the product can make, and it fails in the reassuring
direction, which CLAUDE.md §2.7 identifies as the most damaging way to be wrong.

The same question will recur for every projection field that ships ahead of the machinery
that populates it, so it is worth settling once.

## Decision

**A projection omits a field entirely until something real computes it.** The M4
`CaseOverview` payload carries no `open_issue_count` and no `evidence_coverage`; the fields
join when issue detection and evidence linking do.

Because an omission can still be misread as "nothing to report", the surrounding copy
bounds its own claims rather than implying the list is complete:

- the attention line says "*Of the requirements that need attention*, most are in X", and
  adds "Requirements that haven't been assessed yet aren't counted here" when any are;
- the actions section is titled from what it holds, and states how many actions it is not
  showing rather than implying it shows all of them.

A test asserts the fields are absent, so re-adding them as zeros is a red build rather
than a quiet regression.

## Alternatives rejected

- **Return `0` / `0%`.** Simplest, and matches §44.1's shape immediately. Rejected: a zero
  is an assertion that a count was performed. The client cannot distinguish "no issues"
  from "issues do not exist yet", so it renders the reassuring reading.
- **Return `null` with the field present.** Better than zero — null is at least not a
  count — but it invites `?? 0` at the call site, which reintroduces the zero one layer
  down and makes the honest case the one a developer has to remember. Absence cannot be
  coalesced by accident.
- **Return the field with an explicit `available: false` flag.** Honest and explicit, and
  a reasonable choice. Rejected as premature: it designs the shape of a subsystem that
  does not exist, and M5/M6 will know better what belongs there. Adding a field later is
  cheap; removing one that clients have started reading is not.
- **Show a "coming soon" placeholder in the UI.** Rejected outright. The product does not
  narrate its own roadmap to users — a person preparing a citizenship application is not
  helped by learning which milestone they are in.

## Consequences

- The overview is honest about its own scope, at the cost of not matching §44.1's field
  list until M6. §44.1 is not wrong; it describes the finished projection.
- M5 and M6 must **add** these fields rather than assume they were forgotten. The test
  named `test_issue_count_and_evidence_coverage_are_absent_not_zero` will fail when the
  fields arrive, which is the intended prompt to revisit this ADR and delete it.
- The bounding copy is now load-bearing: if someone later removes "Requirements that
  haven't been assessed yet aren't counted here", the attention line silently widens into
  a claim about the whole case.
- The same rule should apply to any future projection field that ships ahead of its
  subsystem.

## Invariants touched

**CLAUDE.md §2.7 (prefer visible uncertainty to false reassurance).** This ADR is a direct
application: where the product cannot say a thing, it says nothing rather than saying zero.

**CLAUDE.md §2.6 (no readiness score).** Related but distinct. An `evidence_coverage`
percentage would have been a readiness measure in all but name; omitting it now also
avoids introducing one at M5 without a deliberate decision.
