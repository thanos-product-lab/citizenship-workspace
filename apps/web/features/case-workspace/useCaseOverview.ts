"use client";

import { useQuery } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

/**
 * The case overview projection, shared by every reader that needs it.
 *
 * Three components read this now and they sit on different routes: the case header (for
 * currency and the assessed date), the Overview destination (counts and priority
 * actions), and the Requirements destination (per-group summaries). One query key means
 * one request — TanStack dedupes concurrent readers and serves the cache across
 * navigations — and, more importantly, one definition of what "the overview" is.
 *
 * This replaces prop-drilling the payload down from a shell component. With the workspace
 * split across routes there is no longer a common parent to drill from, and threading it
 * through a Next layout would mean the layout fetching data on behalf of pages it does
 * not know about.
 */
export function useCaseOverview(caseId: string) {
  const api = useApiClient();

  return useQuery({
    queryKey: caseKeys.overview(caseId),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/cases/{case_id}/overview", {
        params: { path: { case_id: caseId } },
      });
      // A malformed payload is an error rather than an exception: readers degrade to a
      // named "couldn't load this" state instead of blanking their destination.
      if (!data || !Array.isArray(data.groups)) throw new Error("overview unavailable");
      return data;
    },
  });
}
