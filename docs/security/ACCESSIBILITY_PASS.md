# Accessibility pass — core flows

**Date:** 13 September 2026 (release slice) · **Standard:** WCAG 2.2 AA
**Flows:** case overview · requirement detail · residence table · evidence review · issue queue
**Method:** driven in Chrome against the local stack, on the canonical synthetic case, plus
an automated floor in the test suite.

Two findings, one fixed here. Everything else below was checked and held.

---

## Method, and what each part can and cannot see

**Automated (`jest-axe`, five flows).** Added in this slice. It catches the mechanical
failures — an unlabelled control, a broken ARIA reference, a heading level skipped, a
contrast pair below ratio.

**It is a floor, not the pass.** Automated rules catch on the order of a third of WCAG
failures, and **none of the defects this project's accessibility reviews have actually
found were of that kind**: a label that told a user to act before the screen to act on
existed; a live region overwritten 38ms after it was written; a failure announced only
into a visually-hidden region. Those came from a person using the thing.

It is also scoped to a *component*, not a page: these destinations render an `<h2>` as
their top heading because the `<h1>` belongs to the route layout, so a component-level run
cannot see document-wide heading order, landmark uniqueness, or an id contributed by a
sibling. The in-browser audit below is what covers that.

**In-browser (Chrome, this pass).** Per flow: tab order enumerated against the DOM,
landmarks, heading outline, dangling `aria-*` references, duplicate ids, unlabelled
controls, unnamed SVGs, focusable content inside `aria-hidden`, live regions. Then focus
visibility with real key presses, and a greyscale check on the status surfaces.

---

## Findings

### 1. No skip link — **fixed in this slice**

WCAG 2.4.1 Bypass Blocks (Level A). Every destination repeats **seven tabbable controls**
before its own content — the back link, Update assessment, and six navigation links — so
reaching a requirement row cost eight presses, on every page.

The landmarks (`header`, `nav "Case navigation"`, `main`) satisfy the criterion for anyone
navigating *by landmark*. A keyboard user without a screen reader had no bypass at all.

What makes this worth recording rather than just fixing: **the shell already had the shape
for it.** `ContentShell` put `<main>` around the destination and outside the persistent
header, with a comment reading *"a persistent header is context, and 'skip to main
content' should skip it."* The landmark was positioned for a link that was never added.

Fixed: a skip link rendered from the route layout — a server component, so it is the first
tabbable in the document without waiting on a fetch, and it is present on every lifecycle
branch including the error paths, where a user is most likely to be hunting for a way out.
`<main>` takes `tabIndex={-1}` so focus actually lands there; without it the browser
scrolls to the landmark and leaves focus at the top of the document, and the next Tab
returns to the navigation the user just asked to skip. That is the usual half-working skip
link, and the tests pin against it.

Verified in Chrome: first tabbable in the document, target exists, focus moves to
`MAIN#case-main`. Capture: `docs/demo-assets/m11/`.

### 2. Two `h1`s on the requirement detail — **raised, not fixed**

Every destination renders the case title as `h1` and its own subject as `h2` — except the
requirement detail, which renders the requirement title as a second `h1`:

```
h1 Amara Okonkwo — demo      (route layout, persistent)
h1 Total absences            (page subject)
h2 WHY THIS ASSESSMENT WAS MADE … ×8
```

**Not a strict AA failure.** HTML5 permits multiple `h1`s and axe does not flag it; the
relevant criterion, 1.3.1, asks that structure be programmatically determinable, and it
is. It is a document-outline defect and an inconsistency with the other five destinations.

Two ways to resolve it, and they point in opposite directions:

- **Demote the page subject.** Requirement title → `h2`, stack layers → `h3`. Consistent
  with every other destination, and cheapest. Costs the design intent recorded at M4, that
  the explanation stack's layers are the page's top-level sections.
- **Stop the case title being a heading.** It is persistent chrome in a banner, so arguably
  each destination's subject should be the `h1` — the overview's readiness headline, the
  timeline's title, the requirement's name. More correct information architecture, and it
  touches six destinations and their tests.

Left for a decision rather than chosen here: it is a judgement about heading hierarchy
across the whole workspace, and the release slice is verification and assembly.

### 3. Reflow at 320 CSS px — **not verified in-browser**

Reported as unverified rather than passed. The tab's layout viewport would not follow a
window resize (`outerWidth` changed, `innerWidth` stayed at 1512), so the 1.4.10 check
could not be driven.

Static evidence is good and is not the same as having looked: seven `@media (max-width:
34rem)` breakpoints across the component sheet, and the two wide surfaces scroll
themselves rather than the document —

```css
/* A data table may scroll instead of reflowing (an explicit 1.4.10 exception), but it
   must scroll *itself* rather than making the document scroll sideways. */
.cw-calc-scroll { overflow-x: auto; }
```

**Owed:** one manual pass at 320px and at 200% zoom, on the timeline and the review split
view, which are the two widest layouts.

---

## What was checked and held

**Structure, all five flows.** Landmarks present and correct on every flow (`header`,
`nav "Case navigation"`, `main`). No dangling `aria-labelledby` / `describedby` /
`controls` / `errormessage`. No duplicate ids. No unlabelled inputs. No unnamed SVGs. No
focusable content inside `aria-hidden` — including the timeline band, which is
`aria-hidden` throughout and draws no controls.

**Tab order.** Enumerated on the overview: 15 tabbables, every one with an accessible
name, DOM order matching visual order.

**The residence table.** A real `<table>` with a `<caption>` ("Your trips, earliest
first"), every `th` scoped, 12 rows. The visual band above it is decoration: every value
in it appears in the table in words.

**The issue queue.** Clean `h2 → h3 → h4` nesting, each action group an
`aria-labelledby`-labelled region, and Dismiss carrying the issue name in its accessible
name rather than being one of several identical "Dismiss" buttons.

**Focus indicator.** `:focus-visible` applies a 4px two-tone ring via `box-shadow`, and
the ring is visibly rendered (checked with real Tab presses). Box-shadow is dropped
entirely by Windows High Contrast, so `globals.css` restores a real outline under
`@media (forced-colors: active)` — already present before this pass.

**Status without colour.** Greyscale check on the requirements list: `Supported` and
`Near threshold` are distinguished by glyph *and* word, not hue. Consistent with the M8
work that gave a disputed trip a hatch rather than a colour.

**Reduced motion.** `@media (prefers-reduced-motion: reduce)` covers buttons, requirement
rows, the preview and its change list, the timeline table — and pre-emptively `.cw-band`
and its SVG children, which draw no motion today, so that adding some is covered by
default rather than by someone remembering.

**The dialog primitive.** 20 tests added earlier in this slice, mutation-checked three
ways: ARIA wiring, initial focus, Tab and Shift+Tab wrap, `aria-disabled` staying inside
the trap, Escape, the backdrop target guard, scroll lock and its restoration. Return-focus
stays caller-owned by design — the two call sites answer it differently and correctly, and
each already tests its own answer.
