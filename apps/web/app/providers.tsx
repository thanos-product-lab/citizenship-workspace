"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/**
 * The server-state cache (CLAUDE.md §6: server state via TanStack Query).
 *
 * The client is created inside a `useState` initialiser rather than at module scope so it
 * is per-request on the server and never shared between users — a module-level client
 * would leak one case's data into another's render on a server that handles concurrent
 * requests.
 */
export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // A conclusion is only as good as its inputs, and inputs change from other
            // surfaces on the same page. Nothing here is treated as fresh by default:
            // every read revalidates, and the cache exists to keep the screen populated
            // while that happens, not to avoid asking.
            staleTime: 0,
            refetchOnWindowFocus: true,
            // A 404 is the ownership boundary answering, and a 4xx will not become a 2xx
            // by asking again. Retrying only makes a genuine failure slower to surface.
            retry: (failureCount, error) => {
              const status = (error as { status?: number } | null)?.status;
              if (typeof status === "number" && status >= 400 && status < 500) return false;
              return failureCount < 2;
            },
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
