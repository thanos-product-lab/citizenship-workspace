"use client";

import type { components } from "@cw/api-client";
import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

export type Timeline = components["schemas"]["TimelineResponse"];
export type TimelineTrip = components["schemas"]["TimelineTripResponse"];

/**
 * The residence timeline, or `null` when no application date has been selected.
 *
 * Keyed under `caseKeys.detail(caseId)` like every other case reader, so the blunt
 * `assessmentTouched` invalidation reaches it — a travel edit or a date change moves every
 * figure on this screen, and a reader nobody remembered to wire up is the exact failure
 * that convention exists to prevent.
 */
export function useTimeline(caseId: string) {
  const api = useApiClient();
  return useQuery({
    queryKey: [...caseKeys.detail(caseId), "timeline"],
    queryFn: async (): Promise<Timeline | null> => {
      const { data, error } = await api.GET("/api/v1/cases/{case_id}/timeline", {
        params: { path: { case_id: caseId } },
      });
      if (error) throw new Error("timeline unavailable");
      return data ?? null;
    },
  });
}
