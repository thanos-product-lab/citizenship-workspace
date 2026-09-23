"use client";

import { useAuth, useClerk } from "@clerk/nextjs";
import { createApiClient } from "@cw/api-client";
import { useMemo } from "react";

const BASE_URL = process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8000";

/**
 * How long a request waits for a session that is about to exist. Long enough to cover
 * Clerk activating the session after sign-in; short enough that a genuinely signed-out
 * request still fails promptly with the API's own 401.
 */
export const SESSION_WAIT_MS = 3000;

/** The part of Clerk's client this waits on: its listener, which reports the session. */
interface SessionEvents {
  addListener: (listener: (resources: { session?: unknown }) => void) => () => void;
}

/**
 * Resolve once Clerk reports an active session, or with `false` after `timeoutMs`.
 *
 * Clerk calls a new listener straight away with the current state, and may do so before
 * `addListener` has returned its unsubscribe function. So a session seen on that first call
 * is recorded, and the listener is removed as soon as the handle exists.
 */
export function waitForSession(clerk: SessionEvents, timeoutMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false;
    // An object rather than a `const`: the listener can run before `addListener` returns,
    // and must not touch a binding that does not exist yet.
    const listener: { off?: () => void } = {};
    const finish = (found: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      listener.off?.();
      resolve(found);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    listener.off = clerk.addListener(({ session }) => {
      if (session) finish(true);
    });
    // The first, synchronous call may already have finished before the handle existed.
    if (settled) listener.off();
  });
}

/**
 * Typed API client bound to the current Clerk session: every request carries a
 * fresh bearer token from `getToken()`. All backend calls go through this.
 *
 * **A request waits for a session that is on its way.** `getToken()` already waits for
 * Clerk to load, and returns null only when Clerk holds no session. Straight after signing
 * in with an email code there is a moment where that is true of a user who *is* signed in:
 * Clerk navigates to the app while it is still making the new session active, and the
 * first page's queries went out in that gap with no `Authorization` header. The API
 * answered "Invalid or missing authentication", the cases list said it could not load,
 * and "Try again" worked because by then the session was active.
 *
 * So a request with no token waits, up to `SESSION_WAIT_MS`, for Clerk to report a session,
 * and then asks for the token again. If none arrives the request goes out as it always did
 * and gets the API's 401: nothing about what the API accepts changes, only when this asks.
 */
export function useApiClient() {
  const { getToken } = useAuth();
  const clerk = useClerk();
  return useMemo(() => {
    const client = createApiClient(BASE_URL);
    client.use({
      async onRequest({ request }) {
        let token = await getToken();
        if (!token && (await waitForSession(clerk, SESSION_WAIT_MS))) {
          token = await getToken();
        }
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`);
        }
        return request;
      },
    });
    return client;
  }, [getToken, clerk]);
}
