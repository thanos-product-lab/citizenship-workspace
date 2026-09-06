# ADR-0026 — A hostile PDF's JavaScript runs in the preview, and we accept that for now

**Status:** Accepted · **Date:** 2026-09-06 · **Milestone:** M8 slice 3b

## Context

The review split view embeds a user's own uploaded document in an `<iframe>` so they can
read it while confirming what a model read out of it. Blind confirmation asks them to
read the page and type what it says, so the preview is not decoration — it is the input.

The M8 slice 3b security review measured what that costs. A PDF carrying
`/OpenAction /S /JavaScript` **executes in Chrome's PDF viewer** inside the frame:

| iframe | result |
|---|---|
| no `sandbox` | JS ran — `app.alert` fired |
| `sandbox` (bare) | `ERR_BLOCKED_BY_CLIENT`, no viewer, **PDF does not render** |
| `sandbox` with any token combination tried | identical: blocked |
| `sandbox` + an image | renders normally |

So `sandbox` is not a mitigation here. Its cost is the preview itself, for the product's
primary document type.

## Decision

**Accept the risk for PDFs, bound it, and write it down.** Specifically:

1. **No `sandbox` on the PDF path.** It would remove the feature, not secure it.
2. **A `frame-src` allowlist** (`apps/web/next.config.ts`) so only the object store can be
   framed, plus `object-src 'none'` to close the other route to a plugin.
3. **Inline serving is gated twice** (`app/evidence/service.py::content_url`): the worker
   must have opened the file and found its bytes to be the kind of document they claimed
   (`CONTENT_VERIFIED_STATUSES`), and the response content type is pinned to the type
   validated at upload. The first decides which documents may be interpreted, the second
   as what.
4. **Recorded here rather than left implicit.** Doing nothing and not writing it down was
   the one option the review ruled out.

## What the exposure actually is

The frame is cross-origin — the object store, not the app — so PDFium cannot reach this
app's DOM or its Clerk token. What a hostile "booking confirmation" *can* do is put
attacker-chosen modal text in front of someone inside their own citizenship workspace,
which is phishing carrying the product's endorsement, and prompt navigation via
`app.launchURL`. It also exercises PDFium as an attack surface, which Technical
Architecture RFC §23.4 names ("malicious PDF uploads") and which had no path into the
product before this slice.

The realistic delivery is a document the user uploaded themselves, so this is a weaker
position for an attacker than a link: they must already have persuaded the user to obtain
and upload the file.

## The durable fix, and why it is not in this slice

**PDF.js with `enableScripting: false`.** It is already on the approved stack list
(CLAUDE.md §3), it removes the cross-origin frame and the signed URL from the browser's
plugin path entirely, and it is the thing that would let a source region be highlighted
when a locator exists to highlight. It is a slice of work, not a config line, and slice 3b
was scoped as the review interaction rather than a renderer.

Revisit when: a source locator arrives (the highlight needs PDF.js anyway), or this
product is exposed to documents a user did not choose to upload.

## Consequences

- The preview works for every supported type, which is what the review interaction needs.
- A hostile PDF can show text inside the workspace. Bounded, not eliminated.
- `frame-src` must be kept in step with the deployed storage origin
  (`NEXT_PUBLIC_STORAGE_ORIGIN`); getting it wrong shows an empty frame rather than
  failing open.
