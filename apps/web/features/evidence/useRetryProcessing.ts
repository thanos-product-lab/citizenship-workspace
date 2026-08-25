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
export interface RetryRefusal {
  /** The server's stable code, so the client never has to parse a sentence. */
  code: string;
  /** How long until a retry would be accepted, when the refusal is a cooldown. */
  retryAfterSeconds?: number | undefined;
}

export function useRetryProcessing(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation<unknown, RetryRefusal, string>({
    mutationKey: [...caseKeys.evidence(caseId), "retry"],
    mutationFn: async (evidenceItemId: string) => {
      const { data, error } = await api.POST(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}/retry",
        { params: { path: { case_id: caseId, evidence_item_id: evidenceItemId } } },
      );
      if (!data) {
        // The two refusals below are on the ordinary path, not edge cases:
        // `PARTIALLY_COMPLETED` is retryable and deterministically returns to
        // `PARTIALLY_COMPLETED`, so "retry a scan, watch it come back, retry again"
        // walks straight into the cooldown. Throwing a shaped refusal rather than a bare
        // Error is what lets the screen say which one happened, and for how long.
        const refusal = error as { code?: string; retry_after_seconds?: number } | undefined;
        throw {
          code: refusal?.code ?? "RETRY_FAILED",
          retryAfterSeconds: refusal?.retry_after_seconds,
        } satisfies RetryRefusal;
      }
      return data;
    },
    onSuccess: () => assessmentTouched(client, caseId),
  });
}
