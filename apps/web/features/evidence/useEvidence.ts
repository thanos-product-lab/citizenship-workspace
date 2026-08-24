"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

import { pollInterval, type EvidenceItem } from "./library";

/**
 * The case's evidence library, plus the upload vocabulary the server will accept.
 *
 * Polls while anything is still moving and stops when nothing is — rather than SSE,
 * which the roadmap names and ADR-0020 defers. `EventSource` cannot send an
 * `Authorization` header, and this API authenticates with a Clerk bearer token, so SSE
 * would mean either a credential in a query string (which threat model §6.4 forbids for
 * signed URLs, and the same reasoning applies) or a second auth mechanism with its own
 * CSRF surface. A request every second and a half, only while something is in flight, is
 * a better trade for a screen a user watches for a few seconds.
 */
export function useEvidence(caseId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.evidence(caseId),
    refetchInterval: (query) => {
      const items = (query.state.data?.items ?? []) as EvidenceItem[];
      return pollInterval(items, Date.now());
    },
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
