"use client";

import type { components } from "@cw/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

export type ProposedDate = components["schemas"]["ProposedApplicationDateResponse"];
export type Simulation = components["schemas"]["ApplicationDateSimulationResponse"];
export type SimulatedRequirement = components["schemas"]["SimulatedRequirementResponse"];

/** The case's selected date, or `null` when none has been chosen yet. */
export function useApplicationDate(caseId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: caseKeys.applicationDate(caseId),
    queryFn: async (): Promise<ProposedDate | null> => {
      const { data, error } = await api.GET("/api/v1/cases/{case_id}/application-dates", {
        params: { path: { case_id: caseId } },
      });
      if (error) throw new Error("application date unavailable");
      return data ?? null;
    },
  });
}

/**
 * Preview a candidate date.
 *
 * **This must never call `assessmentTouched`.** Nothing changed — the endpoint writes no
 * row, marks nothing stale and reconciles no issue (Domain §10.3) — so invalidating the
 * case subtree would make every destination refetch to be told exactly what it already
 * knows, and would train the reader of this file to think a preview is a write.
 *
 * The result is held in component state rather than the query cache for the same reason
 * plus one more: a preview is not a fact about the case, and putting it under
 * `caseKeys.detail(caseId)` would place an unsaved figure one cache read away from every
 * component that displays saved ones.
 */
export function useSimulateApplicationDate(caseId: string) {
  const api = useApiClient();
  return useMutation({
    mutationKey: [...caseKeys.detail(caseId), "simulate"],
    mutationFn: async (candidate: string): Promise<Simulation> => {
      const { data, error } = await api.POST(
        "/api/v1/cases/{case_id}/application-dates/simulate",
        {
          params: { path: { case_id: caseId } },
          body: { candidate_application_date: candidate },
        },
      );
      if (error || !data) throw new Error("preview unavailable");
      return data;
    },
  });
}

export type SaveOutcome = { assessedCount: number };

/**
 * Save a previewed date: select it, then recalculate.
 *
 * Two requests, deliberately, and no new server command for the pair. `/select` appends a
 * date version and marks the dependent results STALE in one transaction;
 * `/assessments/recalculate` then produces the new ones. Between them the case is
 * genuinely stale, and if the second call fails that is what the user is left with — which
 * M6 already handles honestly, with a `STALE_ASSESSMENT` item in the queue and a retry.
 * Collapsing the pair into one endpoint would hide a real intermediate state behind a
 * command that cannot express it.
 *
 * **It shares `useRecalculate`'s mutation key on purpose.** `useRecalculationInFlight`
 * reads that key, so the header's Recalculate and the requirements list's Run assessment
 * both disable while a save is running. Without it, saving here leaves a second
 * recalculation one Tab away, which is the concurrency M6 built that federation to close.
 *
 * `expected_revision` is the optimistic-concurrency token from the read. A 409 means the
 * date moved elsewhere since the preview was taken, and the preview is then describing a
 * comparison whose baseline no longer exists — so the caller reloads rather than retrying.
 */
export function useSaveApplicationDate(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();

  return useMutation({
    mutationKey: [...caseKeys.detail(caseId), "recalculate"],
    mutationFn: async (input: {
      applicationDate: string;
      expectedRevision: number | null;
    }): Promise<SaveOutcome> => {
      const selected = await api.POST("/api/v1/cases/{case_id}/application-dates/select", {
        params: { path: { case_id: caseId } },
        body: {
          application_date: input.applicationDate,
          expected_revision: input.expectedRevision,
        },
      });
      if (selected.response?.status === 409) throw new SaveConflict();
      if (!selected.data) throw new Error("the date could not be saved");

      const recalculated = await api.POST("/api/v1/cases/{case_id}/assessments/recalculate", {
        params: { path: { case_id: caseId } },
      });
      if (!recalculated.data || !Array.isArray(recalculated.data.requirements)) {
        // The date *was* saved. Surfacing this as a plain failure would be wrong — the
        // user's change landed and the case is now STALE with a queue item explaining it.
        throw new RecalculationIncomplete();
      }
      return {
        assessedCount: recalculated.data.requirements.filter(
          (row) => row.conclusion !== "NOT_YET_ASSESSED",
        ).length,
      };
    },
    onSettled: async () => {
      // On success and on failure alike. A failure here can mean the date was saved and
      // the recalculation was not, so the cache is out of date either way.
      await assessmentTouched(client, caseId);
    },
  });
}

/** The date changed elsewhere between reading it and saving; the preview's baseline is gone. */
export class SaveConflict extends Error {
  constructor() {
    super("this date changed elsewhere");
    this.name = "SaveConflict";
  }
}

/** The date was saved; the recalculation that follows it was not. */
export class RecalculationIncomplete extends Error {
  constructor() {
    super("saved, but the recalculation did not finish");
    this.name = "RecalculationIncomplete";
  }
}
