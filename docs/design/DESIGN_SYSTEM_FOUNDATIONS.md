# Design

The one design document. Sections 1 to 10 are the visual system: colour, type, spacing, the
status and provenance vocabularies, and the patterns components follow. Section 11 is how the
interface behaves: the rules every screen keeps.

The code cites this document by section number, so sections are never renumbered; new
material is appended. The original UI/UX direction document it replaced is in git history
(`git show 77cc044:docs/design/Evidence_First_Citizenship_Workspace_UI_UX.md`).

The implementation lives in `packages/design-system`:

| File | Holds |
|---|---|
| `src/tokens.css` | raw values as CSS custom properties |
| `src/tokens.ts` | the typed semantic maps (status, currency, provenance, glyph names) |
| `src/components.css` | component styles |
| `src/StatusGlyph.tsx` | the glyph set, resolved from `GlyphName` |
| `src/RequirementStatus.tsx` | conclusion + currency as two badges |
| `src/AssessmentSummary.tsx` | the head of a requirement: status, figure, summary |
| `src/ExplanationStack.tsx` | `ExplanationStack` + `ExplanationLayer` (§11.5) |
| `src/CalculationBreakdown.tsx` | the arithmetic, as a table |
| `src/AssessedInput.tsx` | `AssessedInput` + `ProvenanceBadge` |
| `src/SourceReference.tsx` | the rule version and its guidance citations |
| `src/StaleAssessmentNotice.tsx` | why a conclusion is no longer current |

Section 11.8 gives the direction the tokens make concrete.

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

Never a fraction, ratio or `n of m` — see Design §11.2 for why `4 / 5` is both a readiness
score and a misreading of a failed conclusion. Never a single verdict for the group:
that would be a claim about all its members on the strength of one.

The link is **described by** its state (`aria-describedby`) rather than containing it, so
a screen-reader user listing links hears "Residence" and not a forty-character sentence,
while focusing it still announces how the group stands.

---

## 10. Known gaps

### 10.1 `SourceReference` cannot show a guidance version or retrieval date (M4)

The product requires that "source links display source version and retrieval date".
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

---

## 11. How the interface behaves

The rules every screen keeps. Each is here because code relies on it.

### 11.1 The workspace is destinations, not one page

A case has six destinations in a horizontal navigation: Overview, Timeline, Requirements,
Evidence, Issues and Case data (ADR-0012). The case header above them carries the case's
identity, its application date and whether any result is out of date, so that is visible
wherever the person is (ADR-0013).

### 11.2 No score, and no fraction either

There is never a readiness percentage. The rule is wider than the percent sign: no
fraction, ratio or "4 of 5" anywhere, because a reader converts `4 / 5` to 80% and it hides
a failure as something missing. Counts are of named states, side by side ("1 near threshold
· 3 supported"), and "not yet assessed" is its own count, never the remainder. A group of
requirements never gets a verdict of its own; no rule concludes anything about a group
(ADR-0010).

### 11.3 The overview answers "what now"

The overview leads with the next steps, derived from the case (ADR-0034), and shows at most
three actions from the requirements themselves. When nothing is left it says what the
workspace does not check, never that the case is ready.

### 11.4 Where a value came from is always visible

The interface distinguishes a value the person entered, one a model proposed, one they
confirmed or corrected, one the system calculated, one a document supports, one in
conflict, and one out of date. A model's proposal must never look like a verified fact. The
provenance tokens (§4) are how.

### 11.5 A requirement explains itself

The answer comes first, then the working:

```text
Assessment (the result, its figure and summary)
├── Limitations
├── Next action
├── How this was worked out
├── Answers used
├── Trips used
├── Evidence used
├── Rule used
└── Assessment history
```

Every layer is always shown. An empty layer says so in one line ("None.") rather than
disappearing, because a missing section and an empty one look the same otherwise. The
explanation is the domain model rendered, never a generated paragraph or a tooltip.

### 11.6 Documents

The document list shows, for each document, its type, its processing state, what the
person has decided about the values read from it, and when it was added, with one action
weighted by whether there is work to do. On the review screen the document sits beside the
values, and every value has an explicit state: proposed, confirmed, corrected or rejected.
For values that matter most, the model's reading is not shown until the person has typed
what the document says (blind entry), so they cannot simply accept it.

### 11.7 Issues

Issues are grouped by what the person has to do: resolve to continue, update your
assessment, confirm information, review carefully, or for information only. Every
out-of-date result is one "Update assessment" task, not one issue each (ADR-0033). The language is calm and precise:
say what was found and what it affects. Avoid alarming red banners, "Something went wrong",
reassurance the system cannot back, and legal or technical wording. When the system cannot
assess something it says so plainly and gives no result, which counts as a success.

### 11.8 Dates, numbers, surfaces and icons

Dates, thresholds and calculated figures get deliberate emphasis: the tabular mono face,
never wrapped. Dates read "15 April 2027", never ISO. Surfaces are soft borders and quiet
section backgrounds, not a page of floating cards. Icons are for domain ideas (a
requirement, a document, a trip, a confirmation), each drawn from the one glyph set, and
never generic AI sparkles.

### 11.9 Motion

Motion explains a change of state (a result going out of date, a value moving from
proposed to confirmed) and is never decoration. Anyone who asks for reduced motion gets
none.

### 11.10 States every screen handles

Loading, empty, failed to load, in progress, out of date and not supported are designed
states, not afterthoughts. A failed load must never look like an empty one: "we couldn't
load your documents" and "no documents yet" are different statements.

### 11.11 Accessibility

WCAG 2.2 AA on the core flows. Everything works from the keyboard, status never relies on
colour alone, focus is always visible and never dropped to the page, errors are attached to
their fields, nothing critical lives only in a tooltip, and layouts hold at 320px and 200%
zoom. The timeline is both a picture and an equivalent table.

### 11.12 Writing

Plain, short and exact. One idea per sentence, UK English, "you" for the person. The same
word for the same thing everywhere: a requirement has a **result**, which can be **out of
date**; the person **updates their assessment**; a period abroad is a **trip**. Keep exact
where exactness is the point: confirmed or not, counted or not, a threshold rather than a
limit. No em dashes, and nothing that sounds like a score or a guarantee.
