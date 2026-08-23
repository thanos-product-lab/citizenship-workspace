"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

/** The case's evidence library, plus the upload vocabulary the server will accept. */
export function useEvidence(caseId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.evidence(caseId),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/cases/{case_id}/evidence", {
        params: { path: { case_id: caseId } },
      });
      // Degrade to a named error rather than an empty library: "this case holds no
      // documents" is a claim about the case, and a failed fetch has not earned it.
      // Same reasoning as `useIssueQueue`.
      if (!data || !Array.isArray(data.items)) throw new Error("evidence library unavailable");
      return data;
    },
  });
}
