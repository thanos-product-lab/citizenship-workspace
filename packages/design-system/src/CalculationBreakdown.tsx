/**
 * The arithmetic behind a conclusion, shown as a table rather than a sentence.
 *
 * Dates, thresholds and totals are the *content* of this product, so they get the mono
 * face with `tabular-nums` (DESIGN_SYSTEM_FOUNDATIONS §5) — figures line up column-wise
 * and a date reads as a value rather than as prose.
 *
 * It is a real `<table>`: these are label/value pairs with a header relationship, and a
 * screen-reader user should be able to navigate them as such. UI/UX §15 asks for
 * screen-reader descriptions of calculations specifically.
 *
 * The frontend never computes any of this. Every row comes from the server's
 * `calculation_breakdown` and `summary_parameters` (CLAUDE.md §8: calculations are
 * server-side and authoritative, and the client does not re-derive totals).
 */

import type { JSX } from "react";

export interface CalculationRow {
  label: string;
  value: string;
  /** An optional qualifier, e.g. "confirmed records only". */
  note?: string | undefined;
}

export function CalculationBreakdown({
  rows,
  caption,
}: {
  rows: CalculationRow[];
  caption: string;
}): JSX.Element | null {
  if (rows.length === 0) return null;
  return (
    <table className="cw-calc">
      <caption className="cw-visually-hidden">{caption}</caption>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <th scope="row">
              {row.label}
              {row.note ? <span className="cw-calc__note">{row.note}</span> : null}
            </th>
            <td className="cw-figure">{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
