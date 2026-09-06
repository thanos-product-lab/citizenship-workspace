"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

/**
 * A short-lived signed URL for the document, served `inline` so a frame renders it
 * rather than downloading it.
 *
 * Refetched a little before the signature expires. The URL cannot be revoked once issued
 * (ADR-0018), so its TTL is the whole of its life — and a preview that silently turned
 * into a broken frame midway through a review would look like the document had gone.
 *
 * The URL is never put in the address bar or a `Referer`: it is set as an `<iframe>`
 * `src` and nowhere else. Threat model §6.4 forbids logging signed URLs, and a redirect
 * would put one in browser history.
 */
export function useDocumentPreview(caseId: string, evidenceItemId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.documentPreview(caseId, evidenceItemId),
    queryFn: async () => {
      const { data } = await api.GET(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}/content",
        {
          params: {
            path: { case_id: caseId, evidence_item_id: evidenceItemId },
            query: { disposition: "inline" },
          },
        },
      );
      if (!data?.url) throw new Error("preview unavailable");
      return data;
    },
    // Refresh at 80% of the signature's life, so the frame never holds a dead URL.
    refetchInterval: (query) => {
      const ttl = query.state.data?.expires_in_seconds;
      return ttl ? Math.max(30_000, ttl * 800) : false;
    },
    staleTime: 0,
  });
}
