"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

/**
 * Run a fresh assessment over the whole case.
 *
 * Two surfaces trigger this and they are never visible at the same time: the header's
 * **Recalculate**, once the case has been assessed at least once, and the requirements
 * list's **Run assessment**, which is the first-run affordance inside its empty state.
 * They share this hook rather than each owning a mutation, so there is one definition of
 * what recalculation does to the cache — the failure this project keeps rediscovering is
 * a writer wired to some readers and not others.
 *
 * `busy` deliberately spans the refetch as well as the POST. The mutation resolves, then
 * invalidation triggers refetches, and during that window every destination still shows
 * the previous run's figures. Releasing the control at the halfway point would invite a
 * second click against numbers already being replaced.
 */
export function useRecalculate(caseId: string) {
  const api = useApiClient();
  const client = useQueryClient();
  const [announcement, setAnnouncement] = useState("");

  const mutation = useMutation({
    mutationKey: [...caseKeys.detail(caseId), "recalculate"],
    mutationFn: async () => {
      const { data } = await api.POST("/api/v1/cases/{case_id}/assessments/recalculate", {
        params: { path: { case_id: caseId } },
      });
      if (!data || !Array.isArray(data.requirements)) throw new Error("recalculation failed");
      return data;
    },
    onSuccess: async (data) => {
      // One statement — "this case's assessment state moved" — reaches every reader on
      // every destination, including ones added later that nobody remembered to wire up.
      await assessmentTouched(client, caseId);
      // Badges change in place, which gives a screen-reader user no cue at all, so the
      // completion has to be its own message.
      const current = data.requirements.filter((r) => r.conclusion !== "NOT_YET_ASSESSED").length;
      setAnnouncement(
        `Recalculation finished. ${current} ${current === 1 ? "requirement" : "requirements"} assessed.`,
      );
    },
    onError: async () => {
      setAnnouncement("Recalculation did not complete.");
      // Refetch on failure too. A recalculation that fails server-side now leaves a
      // durable record — a FAILED run and a PROCESSING_FAILURE item in the queue — and
      // without this the user is told to reload the page to find something the app
      // already knows. The same call covers the ambiguous case this hook has always had
      // to allow for: a timeout or a dropped response after the run committed, where the
      // server state moved and the client never heard.
      await assessmentTouched(client, caseId);
    },
  });

  return { mutation, announcement };
}
