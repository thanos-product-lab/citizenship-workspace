"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

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

/**
 * Whether the overview is being refetched **because something changed**: true only while an
 * invalidated overview is on its way back.
 *
 * `isFetching` alone is true for every refetch, and nothing here is cached as fresh
 * (`staleTime: 0`), so each case tab re-reads the overview as it mounts. The header read
 * `isFetching` as "your last change is being worked through" and flashed its Updating
 * banner, which says the figures shown predate your last change, on every tab switch when
 * nothing had changed. A change reaches the overview through `assessmentTouched`, which
 * invalidates it; a tab's check on mount does not. So invalidated-and-fetching is the state
 * that sentence describes, and a routine revalidation stays silent.
 *
 * Read from the query cache at render: the component re-renders when `isFetching` changes,
 * which is exactly when this can change.
 */
export function useOverviewUpdating(caseId: string): boolean {
  const client = useQueryClient();
  const { isFetching } = useCaseOverview(caseId);
  const invalidated = client.getQueryState(caseKeys.overview(caseId))?.isInvalidated ?? false;
  return isFetching && invalidated;
}
