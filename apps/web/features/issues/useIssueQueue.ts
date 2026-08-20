"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

/** The issue queue for one case: open issues grouped by action, plus resolution history. */
export function useIssueQueue(caseId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.issues(caseId),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/cases/{case_id}/issues", {
        params: { path: { case_id: caseId } },
      });
      // Degrade to a named error rather than an empty queue: "nothing needs your
      // attention" is a claim, and a failed fetch has not earned it.
      if (!data || !Array.isArray(data.groups)) throw new Error("issue queue unavailable");
      return data;
    },
  });
}
