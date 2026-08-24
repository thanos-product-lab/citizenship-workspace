"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/**
 * Ask for a document to be read again.
 *
 * **Not optimistic**, for the usual reason and one specific to this call: the server
 * refuses a retry on a state that has nothing to retry — `UNSUPPORTED` most of all, where
 * the same bytes through the same check reach the same answer. Showing the document
 * moving before the server has agreed would show it moving in exactly the cases where it
 * will not.
 *
 * The response comes back in a non-terminal state, so `useEvidence` resumes polling on
 * its own rather than needing to be told.
 */
export function useRetryProcessing(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationKey: [...caseKeys.evidence(caseId), "retry"],
    mutationFn: async (evidenceItemId: string) => {
      const { data } = await api.POST(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}/retry",
        { params: { path: { case_id: caseId, evidence_item_id: evidenceItemId } } },
      );
      if (!data) throw new Error("that document could not be sent for reprocessing");
      return data;
    },
    onSuccess: () => assessmentTouched(client, caseId),
  });
}
