/**
 * Rendering a component that reads server state.
 *
 * Every query in the app hangs off a `QueryClient`, so tests need one too. This builds a
 * fresh client per render — a shared one would leak a resolved query from one test into
 * the next, and the cache-keyed refetch behaviour these tests exist to check would then
 * depend on test order.
 *
 * Retries are off: a test that mocks a failure wants to see the error state immediately,
 * not after the production retry policy has had two more goes.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}

export function renderWithQuery(
  ui: ReactElement,
  options?: RenderOptions & { client?: QueryClient },
): RenderResult & { client: QueryClient } {
  const client = options?.client ?? createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { ...render(ui, { wrapper, ...options }), client };
}
