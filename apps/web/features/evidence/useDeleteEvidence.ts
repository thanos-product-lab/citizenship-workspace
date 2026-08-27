"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/**
 * Delete a document (Domain §51.1).
 *
 * Invalidates the assessment as well as the library, because deletion reaches further
 * than the evidence screen: any trip the document supported becomes unevidenced, and
 * `residence.travel_consistency` goes STALE in the same transaction. A user who deletes a
 * booking and switches to Requirements must not find a conclusion the server already
 * knows is out of date.
 *
 * No optimistic removal. The row disappearing before the server has agreed would be this
 * product telling the user something is gone on the strength of a request in flight — and
 * a failure would then have to put it back, which reads as the deletion having been
 * undone rather than never having happened.
 */
export function useDeleteEvidence(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationFn: async (evidenceItemId: string) => {
      const { error, response } = await api.DELETE(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}",
        { params: { path: { case_id: caseId, evidence_item_id: evidenceItemId } } },
      );
      // 404 covers "already deleted" as well as "never yours", deliberately — an id must
      // not confirm existence. Either way the document is not there, which is the state
      // the user asked for, so the library refresh below tells the truth.
      if (error && response?.status !== 404) throw new Error("delete failed");
      return evidenceItemId;
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: caseKeys.evidence(caseId) });
      void assessmentTouched(client, caseId);
    },
  });
}
