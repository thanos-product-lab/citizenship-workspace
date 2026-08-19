/**
 * The case workspace's destinations, in navigation order.
 *
 * A list rather than hard-coded markup, because the set grows on a known schedule and
 * each addition should be one entry here rather than a structural change.
 *
 * **Evidence is deliberately absent.** It is a destination in the IA brief, but there is
 * no `evidence` module in `services/platform/app/` and the roadmap places Evidence
 * Foundation at M7 — after M6 (issues) and M5 (timeline). A primary destination that
 * leads to an empty room is a promise the product cannot keep, and CLAUDE.md §10 makes
 * the default answer to scope expansion *no*. Until then the evidence-first claim is
 * carried where it is actually true: the "Evidence used" layer on a requirement detail,
 * which states plainly that no documents are linked and every figure rests on dates the
 * user typed.
 */
export interface CaseDestination {
  /** Appended to `/cases/{caseId}`. The empty string is the case root. */
  segment: string;
  label: string;
}

export const CASE_DESTINATIONS: readonly CaseDestination[] = [
  { segment: "", label: "Overview" },
  { segment: "requirements", label: "Requirements" },
  { segment: "data", label: "Case data" },
] as const;

export function destinationHref(caseId: string, segment: string): string {
  return segment ? `/cases/${caseId}/${segment}` : `/cases/${caseId}`;
}

/**
 * Which destination a pathname sits within, or null if none.
 *
 * Matches on the first segment rather than the whole path so that **sub-pages mark their
 * parent current**: a requirement detail at `/cases/{id}/requirements/{key}` is within
 * Requirements, and a nav that highlighted nothing there would tell a screen-reader user
 * they had left the workspace.
 *
 * The requirement key contains a dot and may be percent-encoded; only the first segment
 * is inspected, so neither affects the result.
 */
export function activeSegment(pathname: string, caseId: string): string | null {
  const base = `/cases/${caseId}`;
  if (pathname !== base && !pathname.startsWith(`${base}/`)) return null;

  const rest = pathname.slice(base.length).replace(/^\//, "");
  if (rest === "") return "";

  const first = rest.split("/")[0] ?? "";
  return CASE_DESTINATIONS.some((d) => d.segment === first) ? first : null;
}
