"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

/** One claim as the review screen needs it, with the decision that settled it. */
export interface ReviewClaim {
  id: string;
  evidence_item_id: string;
  claim_type: string;
  journey_index: number;
  /** Null while a high-risk claim is pending — the blind-entry guarantee at the wire. */
  proposed_value: string | null;
  normalised_value: string | null;
  requires_blind_entry: boolean;
  status: string;
  decision: {
    decision: string;
    review_mode: string;
    reason_code: string | null;
    value: string | null;
    reviewed_by: string;
    reviewed_at: string;
  } | null;
}

/**
 * Every claim one document proposed, in any status.
 *
 * Not `GET /claims`, which is the case-wide queue and returns pending claims only. This
 * screen is a document's own history: dropping a field the moment it was decided would
 * leave the user watching a list shrink with no record of what they had just done, and
 * MVP §8.11 asks the split view to show confirmation history.
 *
 * No polling. Nothing changes these rows except this screen's own mutation, which
 * invalidates the key — unlike the library, where a worker is moving underneath.
 */
export function useDocumentClaims(caseId: string, evidenceItemId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.documentClaims(caseId, evidenceItemId),
    queryFn: async () => {
      const { data, response } = await api.GET(
        "/api/v1/cases/{case_id}/evidence/{evidence_item_id}/claims",
        { params: { path: { case_id: caseId, evidence_item_id: evidenceItemId } } },
      );
      // A 404 is a real answer with its own screen — the document was deleted, or was
      // never in this case. Distinguished from a failed fetch, because "this document is
      // gone" and "we could not reach the server" want different words and different
      // controls.
      if (response?.status === 404) throw new DocumentGone();
      if (!data || !Array.isArray(data.items)) throw new Error("claims unavailable");
      return data.items as ReviewClaim[];
    },
    retry: (failureCount, error) => !(error instanceof DocumentGone) && failureCount < 2,
  });
}

/** The document is not there. Thrown rather than returned so it cannot be mistaken for
 *  an empty list, which would render as "nothing needs your decision". */
export class DocumentGone extends Error {
  constructor() {
    super("document gone");
    this.name = "DocumentGone";
  }
}
