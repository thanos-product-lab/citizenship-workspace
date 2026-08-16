/**
 * Query keys, and what invalidates them.
 *
 * The problem this replaces: assessment state has four readers on one page — the case
 * (for its derived phase), the overview, the requirements list, and a requirement's
 * detail — and three writers: a travel-record change, an application-date change, and a
 * recalculation. Every writer invalidates every reader, because a residence write marks
 * results STALE and a recalculation replaces them.
 *
 * Wired by hand that was four `useState` counters threaded through props, and three times
 * during M4 a writer was connected to some readers and not others: the phase pill kept
 * saying "Setting up" after an assessment, the detail page kept showing CURRENT after an
 * edit, the overview kept describing the previous run. Each was the same bug in a new
 * place, and each was found by opening the app rather than by a test.
 *
 * The fix is to name the thing that goes stale rather than the components that read it.
 * `assessmentTouched` below is the single statement "this case's assessment state moved";
 * any reader keyed under `caseKeys.detail(id)` refetches, including readers added later
 * that nobody remembered to wire up.
 */

import type { QueryClient } from "@tanstack/react-query";

export const caseKeys = {
  all: ["cases"] as const,
  list: () => [...caseKeys.all, "list"] as const,
  /** The prefix every case-scoped query hangs off, so one invalidation reaches them all. */
  detail: (caseId: string) => [...caseKeys.all, caseId] as const,
  case: (caseId: string) => [...caseKeys.detail(caseId), "case"] as const,
  overview: (caseId: string) => [...caseKeys.detail(caseId), "overview"] as const,
  requirements: (caseId: string) => [...caseKeys.detail(caseId), "requirements"] as const,
  requirement: (caseId: string, key: string) =>
    [...caseKeys.detail(caseId), "requirements", key] as const,
  applicationDate: (caseId: string) => [...caseKeys.detail(caseId), "application-date"] as const,
  travelRecords: (caseId: string) => [...caseKeys.detail(caseId), "travel-records"] as const,
} as const;

/**
 * Everything derived from this case's assessment state is now out of date.
 *
 * Call after **any** write that can change a conclusion or its currency: a travel-record
 * create/edit/remove, an application-date change, or a recalculation. Deliberately blunt —
 * it invalidates the whole case subtree rather than naming individual readers, because the
 * failure mode this exists to prevent is precisely a reader nobody remembered to name.
 * Selective invalidation is a server concern (M6, ADR-0008), not a client one.
 */
export function assessmentTouched(client: QueryClient, caseId: string): Promise<void> {
  return client.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
}
