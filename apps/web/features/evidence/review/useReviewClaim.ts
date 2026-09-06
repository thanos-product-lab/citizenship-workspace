"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/** The rejection reasons the server accepts (RFC §10), mirrored so a typo is a
 *  compile error rather than a 422 the user meets. */
export type RejectionCode =
  | "VALUE_NOT_PRESENT"
  | "WRONG_FIELD"
  | "WRONG_DOCUMENT"
  | "DUPLICATE"
  | "AMBIGUOUS"
  | "OTHER";

export interface ReviewInput {
  claimId: string;
  /** What the person typed. Required for a blind field; a correction otherwise. */
  enteredValue?: string;
  /** Omitted for a blind field — the server derives CONFIRM or CORRECT from the entry. */
  decision?: "CONFIRM" | "CORRECT" | "REJECT";
  reasonCode?: RejectionCode;
}

export interface ReviewOutcome {
  claim_id: string;
  claim_status: string;
  decision: string;
  review_mode: string;
  value: string | null;
}

/** A refusal the field itself must show, keeping what the user typed. */
export class ReviewRefused extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ReviewRefused";
  }
}

/**
 * Decide about one claim.
 *
 * **One claim per call, and there is no bulk endpoint to call instead** — MVP §8.11
 * forbids bulk confirmation for high-risk date fields, and M8 meets that by there being
 * no batch route at all rather than by a filter that could acquire an exception.
 *
 * Invalidates the whole case subtree on success, not just this document's claims. A
 * review moves more than the field: the document leaves `AWAITING_CONFIRMATION` once
 * nothing is left to decide, so the library row changes too — and from slice 4 a
 * confirmed value will stale an assessment. `assessmentTouched` is deliberately blunt for
 * exactly the reason its docstring gives: the failure this prevents is a reader nobody
 * remembered to name.
 */
export function useReviewClaim(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationFn: async (input: ReviewInput): Promise<ReviewOutcome> => {
      const { data, error, response } = await api.POST(
        "/api/v1/cases/{case_id}/claims/{claim_id}/review",
        {
          params: { path: { case_id: caseId, claim_id: input.claimId } },
          body: {
            entered_value: input.enteredValue ?? null,
            decision: input.decision ?? null,
            reason_code: input.reasonCode ?? null,
          },
        },
      );
      if (error || !data) {
        // The server's own code and words. An unreadable date and an already-decided
        // claim need different answers from the user, and flattening both to "something
        // went wrong" would leave them re-typing a value that was refused for a reason.
        // The generated client types `error` as FastAPI's validation-error shape, which
        // is only one of the bodies this endpoint returns — a domain refusal carries
        // `code` and a string `detail`. Narrowed through `unknown` rather than asserted
        // across two unrelated shapes.
        const body = error as unknown as { code?: string; detail?: string } | undefined;
        throw new ReviewRefused(
          body?.code ?? `HTTP_${response?.status ?? 0}`,
          body?.detail ?? "That could not be recorded. Try again.",
        );
      }
      return data as ReviewOutcome;
    },
    onSuccess: () => {
      void assessmentTouched(client, caseId);
      void client.invalidateQueries({ queryKey: caseKeys.evidence(caseId) });
    },
  });
}
