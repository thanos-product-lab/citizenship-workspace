# Accessibility pass: core flows

**Date:** 13 September 2026, reflow and heading findings closed 19 September · **Standard:** WCAG 2.2 AA
**Flows:** case overview · requirement detail · residence table · evidence review · issue queue
**Method:** driven in Chrome against the local stack, on the canonical synthetic case, plus
an automated floor in the test suite.

Three findings, all now closed. Everything else below was checked and held.

---

## Method, and what each part can and cannot see

**Automated (`jest-axe`, five flows).** Added in this slice. It catches the mechanical
failures: an unlabelled control, a broken ARIA reference, a heading level skipped, a
contrast pair below ratio.

**It is a floor, not the pass.** Automated rules catch on the order of a third of WCAG
failures, and **none of the defects this project's accessibility reviews have actually
found were of that kind**. A label that told a user to act before the screen to act on
existed. A live region overwritten 38ms after it was written. A failure announced only into
a visually-hidden region. Those came from a person using the thing.

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

### 1. No skip link, fixed in this slice

WCAG 2.4.1 Bypass Blocks (Level A). Every destination repeats **seven tabbable controls**
before its own content (the back link, Update assessment, and six navigation links), so
reaching a requirement row cost eight presses, on every page.

The landmarks (`header`, `nav "Case navigation"`, `main`) satisfy the criterion for anyone
navigating *by landmark*. A keyboard user without a screen reader had no bypass at all.

What makes this worth recording rather than just fixing: **the shell already had the shape
for it.** `ContentShell` put `<main>` around the destination and outside the persistent
header, with a comment reading *"a persistent header is context, and 'skip to main
content' should skip it."* The landmark was positioned for a link that was never added.

Fixed: a skip link rendered from the route layout, which is a server component, so it is
the first tabbable in the document without waiting on a fetch, and it is present on every
lifecycle branch including the error paths, where a user is most likely to be hunting for a
way out.
`<main>` takes `tabIndex={-1}` so focus actually lands there; without it the browser
scrolls to the landmark and leaves focus at the top of the document, and the next Tab
returns to the navigation the user just asked to skip. That is the usual half-working skip
link, and the tests pin against it.

Verified in Chrome: first tabbable in the document, target exists, focus moves to
`MAIN#case-main`. Capture: `docs/demo-assets/m11/` (retired; in git history at `a37b05a`).

### 2. Two `h1`s on the requirement detail, now fixed

Every destination renders the case title as `h1` and its own subject as `h2`, except the
requirement detail, which renders the requirement title as a second `h1`:

```
h1 Amara Okonkwo, demo       (route layout, persistent)
h1 Total absences            (page subject)
h2 WHY THIS ASSESSMENT WAS MADE … ×8
```

**Not a strict AA failure.** HTML5 permits multiple `h1`s and axe does not flag it. The
relevant criterion, 1.3.1, asks that structure be programmatically determinable, and it is.
It is a document-outline defect and an inconsistency with the other five destinations.

Two ways to resolve it, and they point in opposite directions:

- **Demote the page subject.** Requirement title to `h2`, stack layers to `h3`. Consistent
  with every other destination, and cheapest.
- **Stop the case title being a heading.** It is persistent chrome in a banner, so arguably
  each destination's subject should be the `h1`: the overview's readiness headline, the
  timeline's title, the requirement's name. More correct information architecture, and it
  touches six destinations and their tests.

**Resolved with the first option**, on 19 September. The requirement title is an `h2` and
the explanation stack's layers moved from `h2` to `h3`.

The second option was rejected on cost rather than on principle: it is better information
architecture and it touches six destinations and their tests, which is a refactor rather
than a fix. The outline is arguably improved either way, because the layers are divisions
*of the requirement* and nesting them under it is what the outline actually describes.
`ExplanationStack` already carried a `headingLevel` prop, so the change was its default.

### 3. Reflow at 320 CSS px, measured, and one real failure found

The tab's layout viewport would not follow a window resize (`outerWidth` changed,
`innerWidth` stayed at 1512), so the first attempt could not drive 1.4.10 at all.

The way round it: load each destination in an **iframe 320px wide**. Media queries inside a
frame evaluate against the frame's own width, so that is a genuine viewport rather than a
simulation.

Measured at 320px and at 640px, the latter being 200% zoom on a 1280 viewport. Seven
destinations. Six reflowed cleanly. **Evidence did not**: 369px of content in a 320px
window, scrolling the page sideways.

The cause was one control. A file input's intrinsic width is its button plus "No file
chosen", and a grid item defaults to `min-width: auto`, so that intrinsic width became a
floor for the whole upload card. `max-width: 100%` was already on the input and could not
help, because a percentage resolves against a parent that is already too wide. `min-width: 0`
fixes it, and the page now reflows at both widths.

Worth noting what that says about the codebase rather than against it. The same class of bug
was already solved deliberately in the review split view, where `.cw-review` uses
`minmax(0, 1fr)` with a comment reading *"a PDF frame and a long extracted value both refuse
to shrink below their content otherwise, and the page starts scrolling sideways"*. The author
knew this failure. It was missed on one form.

**One destination is still unmeasured.** The review split view detaches the renderer when
nested in a probe frame, because it embeds the document viewer and ends up two PDF frames
deep. Verified from its CSS instead: the `minmax(0, 1fr)` above, a `60rem` breakpoint
collapsing to one column well before either test width, and `width: 100%` on the frame. A
single full-width column cannot overflow.

## What was checked and held

**Structure, all five flows.** Landmarks present and correct on every flow (`header`,
`nav "Case navigation"`, `main`). No dangling `aria-labelledby` / `describedby` /
`controls` / `errormessage`. No duplicate ids. No unlabelled inputs. No unnamed SVGs. No
focusable content inside `aria-hidden`, including the timeline band, which is `aria-hidden`
throughout and draws no controls.

**Tab order.** Enumerated on the overview: 15 tabbables, every one with an accessible
name, DOM order matching visual order.

**The residence table.** A real `<table>` with a `<caption>` ("Your trips, earliest
first"), every `th` scoped, 12 rows. The visual band above it is decoration: every value in
it appears in the table in words.

**The issue queue.** Clean `h2 → h3 → h4` nesting, each action group an
`aria-labelledby`-labelled region, and Dismiss carrying the issue name in its accessible
name rather than being one of several identical "Dismiss" buttons.

**Focus indicator.** `:focus-visible` applies a 4px two-tone ring via `box-shadow`, and
the ring is visibly rendered (checked with real Tab presses). Box-shadow is dropped
entirely by Windows High Contrast, so `globals.css` restores a real outline under
`@media (forced-colors: active)`, already present before this pass.

**Status without colour.** Greyscale check on the requirements list: `Supported` and
`Near threshold` are distinguished by glyph *and* word, not hue. Consistent with the M8
work that gave a disputed trip a hatch rather than a colour.

**Reduced motion.** `@media (prefers-reduced-motion: reduce)` covers buttons, requirement
rows, the preview and its change list, and the timeline table. It pre-emptively covers
`.cw-band` and its SVG children, which draw no motion today, so adding some is covered by
default rather than by someone remembering.

**The dialog primitive.** 20 tests added earlier in this slice, mutation-checked three
ways: ARIA wiring, initial focus, Tab and Shift+Tab wrap, `aria-disabled` staying inside
the trap, Escape, the backdrop target guard, scroll lock and its restoration. Return-focus
stays caller-owned by design, because the two call sites answer it differently and
correctly, and each already tests its own answer.
