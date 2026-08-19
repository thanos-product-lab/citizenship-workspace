# Design System Foundations

### Status

Proposed for implementation
Version: 0.3 — token foundation (M1 slice 4) + components (M4 slices 1–2)

This document specifies the token layer: colour, typography, spacing, surfaces,
and the status / provenance vocabularies. The implementation lives in
`packages/design-system`:

| File | Holds |
|---|---|
| `src/tokens.css` | raw values as CSS custom properties |
| `src/tokens.ts` | the typed semantic maps (status, currency, provenance, glyph names) |
| `src/components.css` | component styles |
| `src/StatusGlyph.tsx` | the glyph set, resolved from `GlyphName` |
| `src/RequirementStatus.tsx` | conclusion + currency as two badges |
| `src/AssessmentSummary.tsx` | the head of a requirement: status, figure, summary |
| `src/ExplanationStack.tsx` | `ExplanationStack` + `ExplanationLayer` (UI/UX §7.3) |
| `src/CalculationBreakdown.tsx` | the arithmetic, as a table |
| `src/AssessedInput.tsx` | `AssessedInput` + `ProvenanceBadge` |
| `src/SourceReference.tsx` | the rule version and its guidance citations |
| `src/StaleAssessmentNotice.tsx` | why a conclusion is no longer current |

See `Evidence_First_Citizenship_Workspace_UI_UX.md` §13 for the direction this
makes concrete. `BeforeAfterValue` is the one M4 component still outstanding; it
belongs with the recalculation loop in slice 4.

---

## 1. Principles

- **Calm, not sterile.** Strong hierarchy, generous spacing, a restrained neutral
  foundation, one confident accent. Not a floating-card dashboard.
- **Not default shadcn.** A teal accent over cool-slate neutrals, domain-meaning
  status tokens, and typographic emphasis on dates and calculations — the product
  must not read as stock shadcn/zinc.
- **Colour is never the only signal.** Every status and provenance token pairs a
  hue with a **glyph and a label** (`tokens.ts`). This is a WCAG 2.2 requirement,
  not a preference.
- **One source of truth per concern.** Raw values live once in `tokens.css`;
  `tokens.ts` references variables by name and never re-declares a hex.

---

## 2. Colour

### 2.1 Ramps

- **Neutral** (`--cw-neutral-50 … 950`): cool slate — the calm foundation for
  backgrounds, surfaces, borders, and text.
- **Primary** (`--cw-primary-50 … 900`): a single confident teal accent. Used for
  actions, focus, and the "provisional / preview" and "AI-proposed" provenance.

### 2.2 Role tokens

Components reference **roles**, not ramp steps, so theming flips for free:
`--cw-bg`, `--cw-surface`, `--cw-surface-sunken`, `--cw-border`,
`--cw-border-strong`, `--cw-text`, `--cw-text-muted`, `--cw-text-subtle`,
`--cw-accent`, `--cw-accent-hover`, `--cw-accent-contrast`, `--cw-focus`.

### 2.3 Contrast

All foreground/background pairings target **WCAG 2.2 AA** (≥ 4.5:1 for text,
≥ 3:1 for icons and large text), verified in both light and dark themes —
including each status colour on its own tinted badge surface. The three edge
cases found during authoring (`inconsistent` and `not_yet_assessed` badges in
light; `--cw-text-subtle` in dark) were adjusted until they passed 4.5:1.

---

## 3. Status tokens (requirement conclusion)

Colour + glyph + label for each conclusion state. Hues are muted and
distinguishable; no traffic-light dashboard.

| State | Intent (hue) | Glyph | Colour var |
|---|---|---|---|
| Supported | subdued green | `check` | `--cw-status-supported` |
| Incomplete | neutral blue | `dashed-circle` | `--cw-status-incomplete` |
| Inconsistent | burnt orange | `conflict` | `--cw-status-inconsistent` |
| Near threshold | amber | `gauge` | `--cw-status-near-threshold` |
| Requires judgement | violet | `scale` | `--cw-status-requires-judgement` |
| Professional review recommended | plum | `shield` | `--cw-status-professional-review` |
| Not currently satisfied | restrained red | `minus-circle` | `--cw-status-not-satisfied` |
| Not yet assessed | neutral grey | `dash` | `--cw-status-not-assessed` |

Each has a matching `…-surface` token (a 12% tint over the current surface, so it
re-themes automatically) for badges and panels.

### 3.1 Currency (separate axis)

Currency is **orthogonal** to conclusion (CLAUDE.md §2.4): a result can be
`Supported` *and* `Stale`. Never fold them into one token.

| Currency | Glyph | Colour var |
|---|---|---|
| Current | `dot` | — (no adornment) |
| Stale | `clock` | `--cw-currency-stale` (amber) |
| Superseded | `history` | `--cw-currency-superseded` (grey) |
| Provisional | `preview` | `--cw-currency-provisional` (teal) |

---

## 4. Provenance vocabulary

How a value came to be — the product's core trust signal. Distinct treatment for
each, so an AI proposal is never mistaken for a confirmed fact.

| Kind | Glyph | Colour var |
|---|---|---|
| AI proposed | `proposed` | `--cw-provenance-ai-proposed` |
| User confirmed | `check` | `--cw-provenance-user-confirmed` |
| User corrected | `pencil` | `--cw-provenance-user-corrected` |
| System calculated | `equals` | `--cw-provenance-system-calculated` |
| Evidence supported | `paperclip` | `--cw-provenance-evidence-supported` |
| Conflicting | `conflict` | `--cw-provenance-conflicting` |
| Stale | `clock` | `--cw-provenance-stale` |
| Unavailable | `slash` | `--cw-provenance-unavailable` |

AI-proposed values additionally carry a dashed treatment in M4 components, so the
distinction survives greyscale.

### 4.1 Known gap: no "entered, not yet confirmed" kind

The eight kinds above describe how a value came to be. They have no entry for
**a value the user typed but has not confirmed** — a travel record whose
`review_state` is `DRAFT` or `UNCERTAIN`.

This matters because provenance and the §6.1 trust gate are different questions,
and conflating them produces false labels. A record the user *confirmed* is
`user_confirmed` even when its dates are estimated; the date confidence is a
separate axis, shown on its own line. But a record never confirmed has no honest
token, and the two nearest are both wrong: `user_confirmed` overstates, and
`system_calculated` claims something computed a date the user typed.

M4 falls back to `unavailable` and states the rest in words on the row. That is
least-wrong rather than right. **Decide before M5**, when AI-proposed claims make
the distinction load-bearing: either add a `user_entered` kind here (a change to
this document, then `tokens.ts`), or accept the fallback deliberately and record
why.

---

## 5. Typography

- **Sans** (`--cw-font-sans`): Inter, with a system fallback stack.
- **Mono** (`--cw-font-mono`): IBM Plex Mono — for **dates, thresholds, and
  calculation breakdowns**, set with `font-variant-numeric: tabular-nums` so
  figures align. Dates and calculations are the content; they get deliberate
  emphasis.
- **Scale**: `--cw-text-xs … --cw-text-4xl` (0.75 → 2.25rem).
- **Leading**: `--cw-leading-tight | snug | normal`.
- **Weights**: `--cw-weight-regular | medium | semibold` (400/500/600).

---

## 6. Spacing, radius, elevation

- **Spacing** (`--cw-space-1 … 16`): 4px base scale.
- **Radius** (`--cw-radius-sm … xl`): soft, never pill.
- **Elevation**: prefer borders to shadows; only `--cw-shadow-sm` and
  `--cw-shadow-md`, both soft. `--cw-focus-ring` is a two-layer ring using the
  surface and focus colours so it reads on any background.

---

## 7. Theming

Light by default; dark via the system preference
(`@media (prefers-color-scheme: dark)`) unless overridden, and via an explicit
`:root[data-theme="dark"]` / `[data-theme="light"]` opt-in that always wins. Role
tokens and status bases are re-declared for dark with lighter, AA-verified hues;
ramps are absolute and shared.

---

## 8. Consuming the tokens

```ts
import "@cw/design-system/tokens.css";                 // CSS custom properties
import { statusTokens, provenanceTokens } from "@cw/design-system";
```

Components read role and status tokens, never raw ramp steps or hard-coded hexes.
`tokens.ts` is the single typed bridge between domain states and their visual
treatment, and `GlyphName` is exhaustive over the icon set — a token naming a
glyph `StatusGlyph` does not draw is a compile error, not a missing signal.

---

## 9. Layout and interaction patterns

Patterns that recur across surfaces, recorded here because each has a failure mode
that is invisible once shipped. Screen-level information architecture lives in
`Evidence_First_Citizenship_Workspace_UI_UX.md` §4 and ADR-0012; this section is the
component-level rules that serve it.

### 9.1 Local navigation is links, never ARIA tabs

Destinations within a case are separate pages with their own URLs, document titles
and history entries. Render a `<nav>` with an accessible name and a list of links,
marking the current one with `aria-current="page"`.

**Never `role="tab"` / `tablist`.** It promises assistive technology that the panels
are interchangeable views inside one document, and it suppresses the link semantics
that make bookmarking, open-in-new-tab, and back/forward work.

The current destination is marked **three ways** — `aria-current`, a weight change,
and an underline — because a colour shift alone fails the non-colour rule that
applies to every state in this product, not only assessment states.

A sub-page marks its **parent** current: a requirement detail is within Requirements,
and a navigation highlighting nothing there tells a screen-reader user they have left
the workspace.

### 9.2 A deep link into async content must be resolved after the fetch

A fragment (`#group-RESIDENCE`) is resolved by the browser at navigation time. If the
target is rendered from a client fetch, it does not exist yet, so the jump silently
does nothing and the reader lands at the top of a long page.

Resolve it once the data has arrived, and do **both** halves:

- **move focus** to the target, so the deep link means the same thing to a keyboard or
  screen-reader user as to a sighted one;
- **scroll** to it, which is what a sighted user actually sees.

Scroll **instantly**. An animated scroll here was cancelled before it arrived, leaving
the reader at the top while the focus move had already succeeded — a state that looks
correct to any test asserting only focus. Do not set `scroll-behavior: smooth` globally
to solve a single feature's problem.

### 9.3 A table that reflows keeps its semantics explicitly

Below ~34rem a wide table becomes one record per row rather than columns squeezed into
a phone width. Reflow in **CSS on one DOM** — a screen-reader user is unaffected by
visual layout, so a second copy of the markup solves a problem they do not have while
creating two of everything.

Two rules make it safe:

- **`display: block` strips a table's implicit ARIA roles.** This is the best-known flaw
  in the pattern and it fails silently, turning the table into a pile of divs at exactly
  the width where the layout is hardest to follow. Carry explicit `role="table"`,
  `rowgroup`, `row`, `columnheader` and `cell`. They are no-ops at desktop width.
- **Hide the header row visually, not with `display: none`.** It stays in the
  accessibility tree so each cell keeps its column header; sighted users do not need
  "Destination" above a country name. Give the `<caption>` `display: block` too, or it
  is wrapped in an anonymous table box and shrinks to its longest word.

A concrete reason to prefer one DOM beyond the principled one: focus restoration after
a dialog commonly resolves its trigger by `getElementById`, and with two copies that
returns whichever comes first in the DOM — frequently the hidden one, where `.focus()`
does nothing at all.

### 9.4 Group row anatomy

A row compressing several requirements carries, in order: the group **name** as a link
to that group; **counts of named states**; and a **stale count** when the group has one.

Never a fraction, ratio or `n of m` — see UI/UX §6.2 for why `4 / 5` is both a readiness
score and a misreading of a failed conclusion. Never a single verdict for the group:
that would be a claim about all its members on the strength of one.

The link is **described by** its state (`aria-describedby`) rather than containing it, so
a screen-reader user listing links hears "Residence" and not a forty-character sentence,
while focusing it still announces how the group stands.

---

## 10. Known gaps

### 10.1 `SourceReference` cannot show a guidance version or retrieval date (M4)

MVP §8.8 requires that "source links display source version and retrieval date".
Neither value exists in the data at M4: `RuleVersion.configuration["guidance"]`
holds a citation string only (`{"source": "GUIDE_AN", "section": "…"}`), and the
`GuidanceVersion` / `GuidanceSection` tables that would carry a version and a
retrieval timestamp arrive with Migration 5 (ADR-0007).

`SourceReference` therefore shows the **rule** version and the citation, and says
plainly that the guidance version and retrieval date are not yet recorded. It does
not display a placeholder, an approximate date, or the rule's `effective_from`
dressed as a retrieval date.

This is a deliberate, accepted gap: fabricating provenance is the most damaging
defect available to this product, and an unmet acceptance criterion stated openly
is strictly better than a met one that lies. Closing it is M5 work, and the
criterion should be re-checked then rather than marked complete at M4.
