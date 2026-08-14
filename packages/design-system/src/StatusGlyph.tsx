/**
 * The glyph half of every status signal.
 *
 * `tokens.ts` gives each conclusion, currency and provenance kind a colour *and* a glyph
 * name, because colour must never be the only signal (WCAG 2.2, CLAUDE.md §6). This
 * module resolves those names to real shapes. Each glyph is deliberately distinguishable
 * by silhouette alone — a check, a dashed ring, crossed strokes, a gauge needle — so the
 * set survives greyscale, and no two states read the same at 16px.
 *
 * These are decorative: the components that use them always render a text label beside
 * the glyph, so every icon is `aria-hidden` and the accessible name comes from the label.
 * An icon that needed its own alt text would mean the label was missing.
 *
 * No icon library. UI/UX §13.5 wants icons that support recognition of *domain* concepts,
 * and a generic set has no shape for "near threshold" or "requires judgement".
 */

import type { JSX } from "react";

import type { GlyphName } from "./tokens";

// Exhaustive by construction: `GlyphName` comes from `tokens.ts`, so a token that names a
// glyph missing here fails to compile.
const PATHS: Record<GlyphName, JSX.Element> = {
  // --- conclusions ---
  check: <polyline points="3.5 8.5 6.5 11.5 12.5 4.5" />,
  // A ring of gaps: something is meant to be here and is not yet.
  "dashed-circle": <circle cx="8" cy="8" r="5.5" strokeDasharray="2.6 2.2" />,
  // Crossed strokes: two things that disagree.
  conflict: (
    <>
      <path d="M4 4 12 12" />
      <path d="M12 4 4 12" />
    </>
  ),
  // A dial with the needle swung near the top of its range.
  gauge: (
    <>
      <path d="M2.5 11.5a5.5 5.5 0 0 1 11 0" />
      <path d="M8 11.5 11.4 7.6" />
    </>
  ),
  // Balance scales: a judgement call.
  scale: (
    <>
      <path d="M8 3v10" />
      <path d="M3.5 6h9" />
      <path d="M3.5 6 2 9.5h3z" />
      <path d="M12.5 6 11 9.5h3z" />
    </>
  ),
  shield: <path d="M8 2.5 13 4.5v4c0 3-2.2 4.9-5 5.9-2.8-1-5-2.9-5-5.9v-4z" />,
  "minus-circle": (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M5.5 8h5" />
    </>
  ),
  // A plain rule: nothing has been concluded here.
  dash: <path d="M4 8h8" />,

  // --- currency ---
  dot: <circle cx="8" cy="8" r="2.5" fill="currentColor" stroke="none" />,
  clock: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <polyline points="8 4.8 8 8 10.2 9.6" />
    </>
  ),
  // A clock with an arrow curling back: a version that has been replaced.
  history: (
    <>
      <path d="M2.8 8a5.2 5.2 0 1 0 1.7-3.9" />
      <polyline points="2.4 3.2 2.4 6 5.2 6" />
      <polyline points="8 5.4 8 8 10 9.2" />
    </>
  ),
  // An eye: a preview, not a committed value.
  preview: (
    <>
      <path d="M1.8 8S4 4.2 8 4.2 14.2 8 14.2 8 12 11.8 8 11.8 1.8 8 1.8 8z" />
      <circle cx="8" cy="8" r="1.8" />
    </>
  ),

  // --- provenance ---
  // A dashed ring around a dot: a proposal, not yet a fact.
  proposed: (
    <>
      <circle cx="8" cy="8" r="5.5" strokeDasharray="2.2 2" />
      <circle cx="8" cy="8" r="1.6" fill="currentColor" stroke="none" />
    </>
  ),
  pencil: (
    <>
      <path d="M11.2 2.9 13.1 4.8 5.4 12.5 2.9 13.1 3.5 10.6z" />
      <path d="M10 4.1 11.9 6" />
    </>
  ),
  // Equals: a value derived from others rather than entered.
  equals: (
    <>
      <path d="M4 6.5h8" />
      <path d="M4 9.5h8" />
    </>
  ),
  paperclip: <path d="M11.5 7.2 7.4 11.3a2.6 2.6 0 0 1-3.7-3.7l4.6-4.6a1.7 1.7 0 0 1 2.4 2.4L6.1 10a.9.9 0 0 1-1.2-1.2l4-4" />,
  slash: <path d="M3.5 12.5 12.5 3.5" />,
};

export interface StatusGlyphProps {
  name: GlyphName;
  /** Edge length in px. 16 suits inline badges; 20 suits headings. */
  size?: number;
  className?: string;
}

export function StatusGlyph({ name, size = 16, className }: StatusGlyphProps): JSX.Element {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      // Decorative: the sibling text label carries the meaning.
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
