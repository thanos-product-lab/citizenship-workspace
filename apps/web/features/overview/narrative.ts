/**
 * The readiness narrative, assembled from counts.
 *
 * UI/UX §6.2 asks for "a structured summary rather than a percentage", generated from
 * trusted case state. Two rules keep that honest:
 *
 * 1. **Counts of named states, never a fraction.** "3 supported" and "6 not yet assessed"
 *    are facts. "9 of 15" is a completion measure, and a reader converts it to 60% —
 *    which is the readiness score CLAUDE.md §2.6 forbids, arrived at sideways. The
 *    overview payload carries `total` and `not_yet_assessed` precisely so the UI can say
 *    what has *not* been assessed; rendering them as a ratio would invert that purpose.
 * 2. **No characterisation the system cannot derive.** §6.2's example narrative reads
 *    "Your residence history is broadly complete" — a judgement no rule produces. The one
 *    qualitative statement here is the case *phase*, which is a derived domain value
 *    (ADR-0009), and one line naming which group holds the most outstanding work, which
 *    is a count comparison. Nothing predicts an outcome.
 */

import type { components } from "@cw/api-client";
import { statusTokens, toConclusionState } from "@cw/design-system";

type Overview = components["schemas"]["CaseOverview"];
type Group = components["schemas"]["GroupSummaryView"];

/** Phase → heading. The phase is derived from assessment state, so this is not a verdict
 *  the UI invented; it is the domain's own qualitative state, put into a sentence. */
const PHASE_HEADINGS: Record<string, string> = {
  SETTING_UP: "Setting up your case",
  BUILDING_CASE: "Your case is taking shape",
  RESOLVING_ISSUES: "There’s work to do on your case",
  NEARLY_PREPARED: "Your case is nearly prepared",
  FINAL_REVIEW: "Your case is ready for a final review",
};

export function phaseHeading(phase: string): string {
  return PHASE_HEADINGS[phase] ?? "Your case";
}

export interface CountLine {
  key: string;
  label: string;
  count: number;
}

/**
 * One line per conclusion the case actually contains, using the design system's own
 * labels so the overview and the requirement rows name states identically.
 *
 * `NOT_YET_ASSESSED` is returned separately by `unassessedLine`, never mixed in here —
 * folding it into the tally would let requirements nothing has decided read as progress.
 */
export function conclusionLines(overview: Overview): CountLine[] {
  // Read straight from the server's case-wide list, which is ordered by severity
  // (RULES_SPEC §7.13). Aggregating the per-group lists here instead would preserve each
  // group's order but not the whole: whichever conclusion the first group held would lead,
  // which in practice put SUPPORTED at the top. Neither the aggregation nor the ordering
  // belongs in the client.
  return overview.conclusion_counts.map((entry) => {
    const state = toConclusionState(entry.conclusion);
    return {
      key: entry.conclusion,
      label: state ? statusTokens[state].label : entry.conclusion,
      count: entry.count,
    };
  });
}

/** The unassessed count as its own statement, or null when everything has a conclusion. */
export function unassessedLine(overview: Overview): CountLine | null {
  if (overview.not_yet_assessed === 0) return null;
  return {
    key: "NOT_YET_ASSESSED",
    label: statusTokens.not_yet_assessed.label,
    count: overview.not_yet_assessed,
  };
}

/**
 * Which group holds the most outstanding work, when any does. A count comparison, not a
 * judgement — and null rather than a reassuring sentence when nothing needs attention.
 */
export function busiestGroup(overview: Overview): Group | null {
  const withWork = overview.groups.filter((g) => g.needs_attention > 0);
  if (withWork.length === 0) return null;
  return withWork.reduce((a, b) => (b.needs_attention > a.needs_attention ? b : a));
}

/** A single group's state, in words. Counts only; no verdict about the group. */
export function groupLine(group: Group): string {
  const parts: string[] = [];
  for (const entry of group.conclusion_counts) {
    const state = toConclusionState(entry.conclusion);
    parts.push(
      `${entry.count} ${state ? statusTokens[state].label.toLowerCase() : entry.conclusion}`,
    );
  }
  if (group.not_yet_assessed > 0) {
    parts.push(`${group.not_yet_assessed} not yet assessed`);
  }
  return parts.join(" · ");
}
