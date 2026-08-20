"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/**
 * Set an issue aside.
 *
 * **Not optimistic.** The obvious treatment is to hide the card immediately and roll back
 * on failure, and the plan called for optimistic dismissal with undo. The server refuses
 * to dismiss anything not marked DISMISSIBLE, and refuses a resolved one — so an optimistic
 * hide would show the item leaving the queue in exactly the cases where it must not. The
 * round trip here is one request against a local database; the honesty is worth more than
 * the frame.
 *
 * Undo is a real re-derivation, not a client-side restore: the cause is still present, so
 * the next reconciliation would reopen the issue anyway. Reopening it explicitly keeps the
 * client from having to model a state the server owns.
 */
export function useDismissIssue(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationKey: [...caseKeys.issues(caseId), "dismiss"],
    mutationFn: async (issueId: string) => {
      const { data } = await api.POST(
        "/api/v1/cases/{case_id}/issues/{issue_id}/dismiss",
        { params: { path: { case_id: caseId, issue_id: issueId } } },
      );
      if (!data) throw new Error("dismiss failed");
      return data;
    },
    // The open count on the overview moves too, so the whole case subtree refetches
    // rather than this one query.
    onSuccess: () => assessmentTouched(client, caseId),
  });
}
