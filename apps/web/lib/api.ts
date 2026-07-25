"use client";

import { useAuth } from "@clerk/nextjs";
import { createApiClient } from "@cw/api-client";
import { useMemo } from "react";

const BASE_URL = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8000";

/**
 * Typed API client bound to the current Clerk session: every request carries a
 * fresh bearer token from `getToken()`. All backend calls go through this.
 */
export function useApiClient() {
  const { getToken } = useAuth();
  return useMemo(() => {
    const client = createApiClient(BASE_URL);
    client.use({
      async onRequest({ request }) {
        const token = await getToken();
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
        return request;
      },
    });
    return client;
  }, [getToken]);
}
