"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

export interface UploadInput {
  file: File;
  category: string;
  displayName: string;
}

/**
 * Upload a document: three steps, and the middle one does not go through our API at all.
 *
 *   1. POST .../evidence/uploads  → a presigned PUT URL and a signed token
 *   2. PUT the bytes straight to private object storage
 *   3. POST .../evidence          → the server confirms the object and records it
 *
 * **Not optimistic.** Nothing exists server-side until step 3 succeeds, so showing the
 * document in the library before then would show the user a document the case does not
 * hold — and if step 2 fails, one that never will. The same reasoning as
 * `useDismissIssue`: a round trip is cheaper than a lie.
 *
 * Step 2 is a bare `fetch` rather than the generated client, and that is correct: the
 * URL is the object store's, not our API's, so it is in no OpenAPI schema and must not
 * carry our `Authorization` header. The presigned signature is the only credential it
 * needs, and sending a Clerk token to a third-party host would be a credential leak.
 *
 * `Content-Type` must match exactly what was signed, or the store refuses the PUT —
 * which is the mechanism behind "unsupported file types are rejected before processing".
 */
export function useUploadEvidence(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationKey: [...caseKeys.evidence(caseId), "upload"],
    mutationFn: async ({ file, category, displayName }: UploadInput) => {
      const { data: grant } = await api.POST("/api/v1/cases/{case_id}/evidence/uploads", {
        params: { path: { case_id: caseId } },
        body: { media_type: file.type, declared_size_bytes: file.size },
      });
      if (!grant) throw new Error("could not start the upload");

      const stored = await fetch(grant.upload_url, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": grant.media_type },
      });
      if (!stored.ok) throw new Error("the file could not be uploaded");

      const { data: recorded } = await api.POST("/api/v1/cases/{case_id}/evidence", {
        params: { path: { case_id: caseId } },
        body: {
          upload_token: grant.upload_token,
          category: category as never,
          display_name: displayName,
          original_filename: file.name,
        },
      });
      if (!recorded) throw new Error("the document could not be recorded");
      return recorded;
    },
    // Evidence coverage will feed conclusions from slice 4, and the overview counts
    // change before that. Blunt on purpose — see `assessmentTouched`.
    onSuccess: () => assessmentTouched(client, caseId),
  });
}
