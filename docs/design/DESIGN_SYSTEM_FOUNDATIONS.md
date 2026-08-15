# Design System Foundations

### Status

Proposed for implementation
Version: 0.2 — token foundation (M1 slice 4) + **first components** (M4 slice 1)

This document specifies the token layer: colour, typography, spacing, surfaces,
and the status / provenance vocabularies. The implementation lives in
`packages/design-system`:

| File | Holds |
|---|---|
| `src/tokens.css` | raw values as CSS custom properties |
| `src/tokens.ts` | the typed semantic maps (status, currency, provenance, glyph names) |
| `src/components.css` | component styles — added M4 slice 1 |
| `src/StatusGlyph.tsx` | the glyph set, resolved from `GlyphName` |
| `src/RequirementStatus.tsx` | conclusion + currency as two badges |

See `Evidence_First_Citizenship_Workspace_UI_UX.md` §13 for the direction this
makes concrete. Remaining M4 components (`ExplanationStack`,
`CalculationBreakdown`, `SourceReference`, `StaleAssessmentNotice`,
`AssessmentSummary`, `BeforeAfterValue`) arrive in slice 2.

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

## 9. Known gaps

### 9.1 `SourceReference` cannot show a guidance version or retrieval date (M4)

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
