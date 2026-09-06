"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { documentAssetKeys } from "@/lib/queries";

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
    queryKey: documentAssetKeys.preview(caseId, evidenceItemId),
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
    //
    // Clamped at both ends. The floor stops a very short TTL turning this into a request
    // every few seconds; the ceiling stops the floor *exceeding* the TTL if
    // `storage_presign_ttl_seconds` is ever lowered below about 37 seconds, which would
    // make the frame reliably hold a URL that had already expired — a config change
    // silently breaking the preview.
    refetchInterval: (query) => {
      const ttl = query.state.data?.expires_in_seconds;
      if (!ttl) return false;
      return Math.min(Math.max(30_000, ttl * 800), ttl * 900);
    },
    staleTime: 0,
  });
}
