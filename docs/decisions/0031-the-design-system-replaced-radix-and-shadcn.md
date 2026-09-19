# ADR-0031: The design system is hand built, not Radix and shadcn/ui

**Status:** Accepted, recorded retroactively during the release slice, 19 September 2026
**Supersedes:** the component layer named in `CLAUDE.md` §3 and the Technical Architecture RFC
**Found by:** the release gate audit, which had to check "the product does not resemble a
default shadcn dashboard" and discovered shadcn was never installed

## Context

Both the operating manual and the architecture RFC name **Radix and shadcn/ui (owned, not
default-looking)** as the component layer. Neither is a dependency and neither ever was.
`apps/web/package.json` lists Clerk, TanStack Query, Next, React and the workspace's own
`@cw/design-system`. Tailwind is present and used for layout utilities only.

What exists instead is twelve components carrying domain meaning, 2,538 lines of component
CSS, and a token file: `RequirementStatus`, `EvidenceState`, `AssessedInput`,
`AssessmentSummary`, `ExplanationStack`, `ExtractedFieldReview`, `IssueCard`,
`CalculationBreakdown`, `SourceReference`, `StaleAssessmentNotice`, `BeforeAfterValue`,
`StatusGlyph`.

This was never decided. It was drifted into, one component at a time, and nobody wrote it
down. Recording it now because `CLAUDE.md` §0 says the documents win where they disagree
with the code, and leaving the RFC describing a library nobody used would have the next
person install it.

## Decision

**Keep the hand built design system. Amend the documents.**

The reason the substitution turned out to be right is narrower than "we prefer our own", and
worth stating precisely.

**The components this product needs are not the components a UI kit ships.** A kit gives a
dialog, a select, a badge. What carries this product is `RequirementStatus`, which renders
one of nine named conclusion states beside a currency that varies independently, never by
colour alone, with a glyph per state. And `ExtractedFieldReview`, whose whole behaviour is
that for a high risk claim it renders an **empty box** and refuses to display a value it
was handed. Neither is a restyled kit component. Both encode rules from the domain model.

**The gate is about resemblance, and the surest way to pass it is not to start there.** MVP
§15 asks that the product not look like a default shadcn dashboard. Owning the primitives
means there is no default to escape.

**The accessibility work had to be ours anyway.** The release slice found the modal shell's
mechanics untested, then wrote twenty tests against the trap, Escape, the backdrop guard and
the scroll lock, and mutation checked three of them. Radix would have supplied that for
free and correctly. That is the real cost of this decision and it should be stated: **we
rebuilt a solved problem, and we had to test it ourselves to know it worked.**

## What was given up

- **Dialog, combobox and focus management for free.** All three are hand rolled. `Dialog.tsx`
  exists because `showModal()` is not implemented in jsdom and the accessibility gate runs
  there, which is a reason, and it is not the same reason as "a kit would be worse".
- **Community scrutiny.** Radix's focus trap has been read by thousands of people. Ours has
  been read by one, plus the tests written for it after a gate found it untested.

## Consequences

- `CLAUDE.md` §3 and the Technical Architecture RFC need amending to name the design system
  rather than Radix and shadcn. Until that lands, this ADR is the source of truth and the
  documents are wrong.
- The rejected-technology list in `CLAUDE.md` §10 is unaffected. Nothing here argues against
  a component library in general; it records what this repository actually did.
- If a future slice needs a genuinely complex primitive, a combobox with async loading or a
  virtualised list, reaching for Radix for that one component is not a reversal of this
  decision. The decision is about the domain components, not about never taking a
  dependency.
