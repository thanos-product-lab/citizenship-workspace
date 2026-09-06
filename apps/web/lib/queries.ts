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
  overview: (caseId: string) =>
    [...caseKeys.detail(caseId), "overview"] as const,
  requirements: (caseId: string) =>
    [...caseKeys.detail(caseId), "requirements"] as const,
  issues: (caseId: string) => [...caseKeys.detail(caseId), "issues"] as const,
  evidence: (caseId: string) =>
    [...caseKeys.detail(caseId), "evidence"] as const,
  requirement: (caseId: string, key: string) =>
    [...caseKeys.detail(caseId), "requirements", key] as const,
  /** One document's claims. Under the case subtree, because a decision genuinely changes
   *  case state and every other reader of it should hear. */
  documentClaims: (caseId: string, itemId: string) =>
    [...caseKeys.detail(caseId), "evidence", itemId, "claims"] as const,
  applicationDate: (caseId: string) =>
    [...caseKeys.detail(caseId), "application-date"] as const,
  travelRecords: (caseId: string) =>
    [...caseKeys.detail(caseId), "travel-records"] as const,
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
/**
 * A document's rendered content: the signed preview URL and the extracted text.
 *
 * **Deliberately outside `caseKeys.detail`**, which is the one place in this file that
 * breaks the "hang everything off the case" rule, so it needs its reason written down.
 *
 * `assessmentTouched` invalidates the whole case subtree by design — the failure it
 * prevents is a reader nobody remembered to name. But these two are not case *state*:
 * the preview is a short-lived credential, and re-minting it changes the `<iframe src>`
 * and reloads the PDF. Under the case prefix, confirming field 1 of 6 threw the reader
 * back to page 1 of the document they were reading the answer off — on the one screen
 * whose entire task is "read this and type what it says", getting more expensive with
 * every field, which is precisely the pressure that produces guessing.
 *
 * The claims list is refetched explicitly by the review screen, so the blunt
 * invalidation was buying nothing here that it was not also charging for.
 */
export const documentAssetKeys = {
  preview: (caseId: string, itemId: string) =>
    ["document-assets", caseId, itemId, "preview"] as const,
  text: (caseId: string, itemId: string) =>
    ["document-assets", caseId, itemId, "text"] as const,
} as const;

export function assessmentTouched(
  client: QueryClient,
  caseId: string,
): Promise<void> {
  return client.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
}
