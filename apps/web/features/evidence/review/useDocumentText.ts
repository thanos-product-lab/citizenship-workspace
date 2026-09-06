"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { documentAssetKeys } from "@/lib/queries";

/**
 * The text a deterministic parser read out of the document.
 *
 * **The accessible equivalent of the preview, not a convenience.** Blind confirmation
 * asks a person to read the page and type what it says, and an embedded PDF is not
 * reliably readable by a screen reader — without this, the one interaction the trust
 * model rests on is unusable for some users.
 *
 * `enabled` so it is not fetched until the reader asks for it: this is the only response
 * in the product that carries a document's words, and a tab nobody opened should not pull
 * one over the wire.
 */
export function useDocumentText(
  caseId: string,
  evidenceItemId: string,
  enabled: boolean,
) {
  const api = useApiClient();

  return useQuery({
    queryKey: documentAssetKeys.text(caseId, evidenceItemId),
    enabled,
    queryFn: async () => {
      const { data, response } = await api.GET(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}/text",
        {
          params: {
            path: { case_id: caseId, evidence_item_id: evidenceItemId },
          },
        },
      );
      // 404 means there is no readable text — a scan with no text layer. A real answer
      // with its own words, not a failure: an empty panel would invite someone to
      // "read" a blank and confirm what they thought they saw.
      if (response?.status === 404) return null;
      if (!data) throw new Error("text unavailable");
      return data;
    },
  });
}
