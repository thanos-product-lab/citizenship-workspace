/**
 * The case workspace's destinations, in navigation order.
 *
 * A list rather than hard-coded markup, because the set grows on a known schedule and
 * each addition should be one entry here rather than a structural change.
 *
 * Issues joined at M6, ordered after Requirements: the queue is about the conclusions,
 * so it reads second.
 *
 * Timeline joined at M5, second — the position UI/UX §4 gives it. It sits before
 * Requirements because it shows the *inputs* every residence conclusion is drawn from,
 * and the order of the nav is the order of the argument: here is what you told us, here
 * is what follows from it, here is what needs attention, here is where you change it.
 *
 * Evidence joined at M7, after Requirements and before Issues: a document is something
 * the user provides in support of a conclusion, so it reads alongside the conclusions
 * rather than after the queue of problems with them. It was deliberately absent until
 * then — a primary destination leading to an empty room is a promise the product cannot
 * keep — and the room is now furnished: documents can be uploaded, listed and opened.
 *
 * What it still does not claim is coverage. Nothing links a document to a requirement or
 * a trip until slice 4, so the "Evidence used" layer on a requirement detail continues to
 * say plainly that no documents are linked and every figure rests on dates the user typed.
 * That layer changes when it becomes untrue, not when this destination appears.
 */
export interface CaseDestination {
  /** Appended to `/cases/{caseId}`. The empty string is the case root. */
  segment: string;
  label: string;
}

export const CASE_DESTINATIONS: readonly CaseDestination[] = [
  { segment: "", label: "Overview" },
  { segment: "timeline", label: "Timeline" },
  { segment: "requirements", label: "Requirements" },
  { segment: "evidence", label: "Evidence" },
  { segment: "issues", label: "Issues" },
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
