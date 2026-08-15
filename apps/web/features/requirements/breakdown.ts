/**
 * Turning a result's `calculation_breakdown` and `summary_parameters` into display rows.
 *
 * **This selects and labels; it never calculates.** Every value here is passed through
 * from the server, which owns all arithmetic (CLAUDE.md §8). The one derived value is the
 * unconfirmed *difference* between the provisional and confirmed totals, and it is shown
 * only as a way of naming records that did not count — never as a new total.
 *
 * The `days` / `provisional_days` distinction is the trap this module exists to handle.
 * `days` counts confirmed records only; `provisional_days` includes records that have not
 * been confirmed. They are equal in the canonical case, so rendering the wrong one is
 * invisible in every demo. Each row therefore says which records it counts.
 */

import type { CalculationRow } from "@cw/design-system";

import { formatDate } from "./dates";

type Params = Record<string, unknown>;

function num(params: Params, key: string): number | null {
  const value = params[key];
  return typeof value === "number" ? value : null;
}

function text(params: Params, key: string): string | null {
  const value = params[key];
  return typeof value === "string" ? value : null;
}

function days(count: number): string {
  return count === 1 ? "1 day" : `${count} days`;
}

export function buildCalculationRows(
  breakdown: Params,
  parameters: Params,
): CalculationRow[] {
  const rows: CalculationRow[] = [];

  const applicationDate = text(breakdown, "application_date");
  if (applicationDate) {
    rows.push({ label: "Proposed application date", value: formatDate(applicationDate) });
  }

  // The qualifying-period rule owns the window derivation every other residence rule cites.
  const qStart = text(breakdown, "qualifying_period_start");
  const qEnd = text(breakdown, "qualifying_period_end");
  if (qStart && qEnd) {
    rows.push({
      label: "Five-year qualifying period",
      value: `${formatDate(qStart)} to ${formatDate(qEnd)}`,
      note: text(breakdown, "derivation") ?? undefined,
    });
  }

  const fStart = text(breakdown, "final_year_start");
  const fEnd = text(breakdown, "final_year_end");
  if (fStart && fEnd) {
    rows.push({
      label: "Final twelve months",
      value: `${formatDate(fStart)} to ${formatDate(fEnd)}`,
    });
  }

  // The window a threshold rule measured over travels in summary_parameters, not the
  // breakdown, because only the qualifying-period rule produces a breakdown.
  const wStart = text(parameters, "window_start");
  const wEnd = text(parameters, "window_end");
  if (wStart && wEnd && !qStart) {
    rows.push({ label: "Period measured", value: `${formatDate(wStart)} to ${formatDate(wEnd)}` });
  }

  const presence = text(parameters, "physical_presence_date") ?? text(breakdown, "physical_presence_date");
  if (presence) {
    rows.push({
      label: "First day of the qualifying period",
      value: formatDate(presence),
      note: "the day presence is tested on",
    });
  }

  const tripCount = num(parameters, "trip_count");
  if (tripCount !== null) {
    rows.push({
      label: "Travel records read",
      value: String(tripCount),
      note: "every active record, confirmed or not",
    });
  }

  const confirmed = num(parameters, "days");
  if (confirmed !== null) {
    rows.push({
      label: "Days outside the UK",
      value: days(confirmed),
      note: "from confirmed records only",
    });
  }

  const provisional = num(parameters, "provisional_days");
  if (provisional !== null && confirmed !== null && provisional > confirmed) {
    rows.push({
      label: "Additional days unconfirmed records would add",
      value: days(provisional - confirmed),
      note: "not counted towards the figure above",
    });
  }

  const threshold = num(parameters, "threshold");
  if (threshold !== null) {
    rows.push({ label: "Standard threshold", value: days(threshold) });
  }

  const earliest = text(parameters, "earliest_application_date");
  if (earliest) {
    rows.push({ label: "Earliest date the holding period allows", value: formatDate(earliest) });
  }

  const resolving = text(parameters, "resolving_application_date");
  if (resolving) {
    rows.push({
      label: "Nearest date clear of confirmed absence",
      value: formatDate(resolving),
    });
  }

  return rows;
}
