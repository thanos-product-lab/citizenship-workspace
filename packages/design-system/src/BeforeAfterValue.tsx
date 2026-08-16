/**
 * A figure that changed between two assessment runs.
 *
 * The canonical demo moment is 439 → 440: a trip's return date moves by one day, the total
 * absences recalculate, and **the conclusion does not change** — both runs band as
 * `NEAR_THRESHOLD`. Rendered as conclusions alone, the history reads
 * "Near threshold → Near threshold", i.e. as nothing having happened. The figures are the
 * only thing that makes the change legible, which is why `summary_parameters` is carried
 * on history rows at all.
 *
 * Three rules the component keeps:
 *
 * - **The old value is not struck through.** A superseded figure is not wrong — it was
 *   correct under the inputs of its run, and the product's whole claim is that historical
 *   results stay inspectable. Strikethrough would read as a correction.
 * - **No direction is asserted beyond the arithmetic.** It shows what the figure was and
 *   what it is. It does not say "improved", "worse", or how far from a threshold — that
 *   would be the component drawing a conclusion the rules did not.
 * - **Colour is never the signal.** The arrow is a glyph with a text label behind it, and
 *   the two values are distinguished by position and label, not hue.
 */

import type { JSX } from "react";

export interface BeforeAfterValueProps {
  /** What changed, e.g. "Days outside the UK". */
  label: string;
  /** The value the earlier run reached, formatted. */
  before: string;
  /** The value the later run reached, formatted. */
  after: string;
}

export function BeforeAfterValue({ label, before, after }: BeforeAfterValueProps): JSX.Element {
  return (
    <p className="cw-change">
      <span className="cw-change__label">{label}</span>
      <span className="cw-change__values">
        <span className="cw-change__before cw-figure">{before}</span>
        {/* The arrow is decorative; "changed to" carries the relationship for a screen
            reader, which would otherwise hear two numbers with nothing between them. */}
        <span aria-hidden="true" className="cw-change__arrow">
          →
        </span>
        <span className="cw-visually-hidden">changed to</span>
        <span className="cw-change__after cw-figure">{after}</span>
      </span>
    </p>
  );
}
