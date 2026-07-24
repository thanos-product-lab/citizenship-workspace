# ADR-0001: Stale is a currency, not a conclusion

**Status:** Accepted
**Date:** 2026-07-24
**Milestone:** M3B (first enforced), documentation reconciliation

## Context

Several documents listed "Stale" alongside `Supported`, `Incomplete`, and the
other requirement conclusions, as though it were one more value in the same enum.

This contradicts a core project invariant. Domain Model RFC §3.5 and CLAUDE.md
§2.4 state that a result has two independent dimensions: a **conclusion** (what
we concluded) and a **currency** (whether that conclusion is still current). They
are orthogonal. The canonical illustration is a result that is `SUPPORTED` and
`STALE` at the same time — supported under inputs that have since changed.

If "Stale" is modelled as a conclusion, that state becomes unrepresentable: a
result forced to be *either* `SUPPORTED` *or* `STALE` loses its conclusion the
moment its inputs change, and the historical conclusion — which the product
promises to preserve — is destroyed.

## Decision

Model and document conclusion and currency as two separate axes everywhere.

- Conclusion enum: `SUPPORTED`, `INCOMPLETE`, `INCONSISTENT`, `NEAR_THRESHOLD`,
  `REQUIRES_JUDGEMENT`, `PROFESSIONAL_REVIEW_RECOMMENDED`,
  `NOT_CURRENTLY_SATISFIED`, `NOT_YET_ASSESSED`.
- Currency enum: `CURRENT`, `STALE`, `SUPERSEDED`, `PROVISIONAL`.

Documentation that lists them together is corrected to two lists (see
reconciliation Item 7).

## Alternatives rejected

- **A single status enum including STALE.** Simpler to render, but it makes
  `SUPPORTED + STALE` unrepresentable and discards historical conclusions — the
  exact failure the trust model exists to prevent.
- **A boolean `is_stale` beside a status enum.** Works mechanically, but the
  domain already needs `SUPERSEDED` and `PROVISIONAL`, which a boolean cannot
  express. A currency enum is the honest shape.

## Consequences

- The UI must render two signals per result and never collapse them.
- Every API projection carries both; no endpoint may return a stale result in a
  field the client treats as current.
- This is now enforced by `trust-model-reviewer` and is a milestone-gate question
  at M6.

## Invariants touched

CLAUDE.md §2.4 (conclusion and currency separate). This ADR strengthens it by
removing documentation that contradicted it. The invariant itself is unchanged.

## Footnote

This drift was caught by the pre-build documentation audit, not in code — the
architecture's own principle flagged a document that violated it. That is the
intended behaviour and a point worth making in the case study.
