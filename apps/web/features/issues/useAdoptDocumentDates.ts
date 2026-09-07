"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/** A refusal the card must show rather than flatten to "something went wrong". */
export class AdoptionRefused extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "AdoptionRefused";
  }
}

/**
 * Resolve a conflict by taking the attached document's dates as the trip's.
 *
 * **No body, deliberately.** The disagreement is already determined by the case's own
 * state, so there is nothing for the client to choose — and letting it name the dates would
 * make this an edit wearing a resolution's name, one that could write any date at all while
 * recording `entry_source = CONFIRMED_CLAIM`.
 *
 * **Not optimistic**, for the reason `useDismissIssue` gives and one more. The server
 * refuses with 409 when nothing is in conflict, and the queue this is offered from can be a
 * few seconds stale — so the case where an optimistic update would be wrong is exactly the
 * case this action exists to handle honestly.
 *
 * Invalidates the whole case subtree: adopting writes a new `TravelRecordVersion`, which
 * stales every residence result, moves the absence totals once recalculated, changes the
 * timeline, and clears this issue. Naming those readers individually is how one gets
 * forgotten.
 */
export function useAdoptDocumentDates(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationKey: [...caseKeys.issues(caseId), "adopt-document-dates"],
    mutationFn: async (travelRecordId: string) => {
      const { data, error, response } = await api.POST(
        "/api/v1/cases/{case_id}/travel-records/{travel_record_id}/adopt-document-dates",
        {
          params: {
            path: { case_id: caseId, travel_record_id: travelRecordId },
          },
        },
      );
      if (error || !data) {
        // The generated client types `error` as FastAPI's validation shape, which is only
        // one of the bodies this endpoint returns; a domain refusal carries `code` and a
        // string `detail`. Narrowed through `unknown` rather than asserted between two
        // unrelated shapes.
        const body = error as unknown as
          { code?: string; detail?: string } | undefined;
        throw new AdoptionRefused(
          body?.code ?? `HTTP_${response?.status ?? 0}`,
          body?.detail ?? "That could not be applied. Try again.",
        );
      }
      return data;
    },
    onSuccess: () => assessmentTouched(client, caseId),
  });
}
