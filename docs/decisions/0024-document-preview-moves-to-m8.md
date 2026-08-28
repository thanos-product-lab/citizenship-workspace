# ADR-0024: Document preview moves to M8, where there is something to review it against

**Status:** Accepted
**Date:** 2026-08-28
**Milestone:** M7 (Evidence Foundation) — moving scope to M8

## Context

`IMPLEMENTATION_ROADMAP.md` lists **"derived previews"** in M7's platform scope (line 548)
and **"document preview"** in its frontend scope (line 553). M7 built neither, and unlike
SSE — which ADR-0020 deliberately deferred behind polling, with a recorded reason — nothing
recorded a decision. It simply did not happen.

That is the problem this ADR exists to fix. A capability that quietly fails to appear is
indistinguishable from one that was cut on purpose, and the difference matters at a
milestone gate whose whole question is whether the work is defensible.

The only place the UI/UX direction describes preview is **§9.4, "Document review split
view"**: a preview pane on the left, extracted fields with Confirm and Correct on the
right. Every element on the right-hand side is M8 — `ExtractedClaim`, `ClaimReviewDecision`,
the claim→fact path.

## Decision

**Move derived previews and document preview to M8, and say so in the roadmap.**

A preview in M7 would render a document beside nothing. The user can already see what the
system made of a file — category, processing state, page count, characters read, the
extracted text — and none of that needs the pixels. The reason to look at the *page* is to
check a proposed value against the place it came from, and there are no proposed values
until M8.

Put the other way: preview is not a viewer, it is **evidence for a review decision**. Built
a milestone early it would be a PDF viewer we own for no stated purpose, and the temptation
would then be to justify it by adding a viewing flow the MVP scope does not ask for.

## Consequences

- M7's frontend scope is met without it: library, upload, processing states, retry, delete,
  unsupported state. The review-queue placeholder remains the M8 seam.
- M8 gains the work. Its acceptance criteria should require the preview to render **the
  exact file version a claim was extracted from**, since a preview of a superseded version
  beside a claim from another would be a provenance defect wearing a UI.
- **Derived previews (thumbnails, page images) are not automatically in scope at M8
  either.** The split view needs a rendered page, which PDF.js does client-side from the
  original bytes. Server-side derived images are a separate decision with its own storage,
  lifecycle and deletion obligations — a derived image is as much the user's content as the
  original, and §51.1 would have to destroy it too. Nobody should read this ADR as having
  approved that.
- The retained `storage_key` and the short presigned download TTL already support fetching
  original bytes for a client-side render, so M8 needs no new storage surface for the
  preview itself.

## Alternatives rejected

**Build a minimal preview in M7 to satisfy the roadmap literally.** Scope discipline
(CLAUDE.md §10) asks what core problem an addition solves. This one solves none until there
is a claim to check, and the roadmap is a plan rather than a contract — the correct response
to a plan that no longer fits is to amend it, not to satisfy its wording.

**Leave it unrecorded and let M8 pick it up.** The failure mode this ADR is written
against. Two reviewers and a gate review all had to rediscover that the item was missing.

## Invariants touched

None. Preview reads bytes the user already owns through a path that already exists.
Recorded because CLAUDE.md §12 asks for an ADR on a meaningful deviation, and a milestone
quietly not building two items of its own stated scope is one.
