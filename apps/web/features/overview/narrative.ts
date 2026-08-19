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

/**
 * The readiness headline: how many requirements need the user, in a sentence.
 *
 * This replaces the phase-derived prose heading. The phase is still shown — once, as the
 * pill beside the case title — and restating it here was the page's clearest redundancy.
 *
 * `needs_attention` is the server's count, not a bucket assembled here. It excludes
 * `NEAR_THRESHOLD`, which sits below the attention boundary
 * (`severity(REQUIRES_JUDGEMENT)`) because a near-threshold figure is a caution and not
 * something the user can act on. Grouping it in would overstate by one and disagree with
 * both the phase ladder and `GroupSummaryView.needs_attention`.
 *
 * The three no-attention cases are deliberately distinct. "Nothing needs your attention"
 * is only true when everything has been assessed; while requirements remain unassessed
 * the sentence has to say what it is scoped to, or it reads as an all-clear the engine
 * has not given.
 */
export function readinessHeadline(overview: Overview): string {
  const assessed = overview.conclusion_counts.reduce((total, c) => total + c.count, 0);
  if (assessed === 0) return "This case hasn’t been assessed yet";

  const needs = overview.needs_attention;
  if (needs > 0) {
    return needs === 1
      ? "1 requirement needs your attention"
      : `${needs} requirements need your attention`;
  }
  return overview.not_yet_assessed > 0
    ? "Nothing assessed so far needs your attention"
    : "Nothing needs your attention";
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
