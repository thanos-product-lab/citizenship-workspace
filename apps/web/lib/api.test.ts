import { afterEach, describe, expect, it, vi } from "vitest";

import { waitForSession } from "./api";

type Listener = (resources: { session?: unknown }) => void;

/** A stand-in for Clerk's listener API that lets the test say when a session appears. */
function aClerk(initial: unknown = null) {
  const listeners = new Set<Listener>();
  const off = vi.fn();
  return {
    off,
    addListener(listener: Listener) {
      listeners.add(listener);
      // Clerk calls a new listener straight away with the current state.
      listener({ session: initial });
      return () => {
        off();
        listeners.delete(listener);
      };
    },
    activate() {
      for (const listener of [...listeners]) listener({ session: { id: "sess_1" } });
    },
    get listening() {
      return listeners.size;
    },
  };
}

afterEach(() => vi.useRealTimers());

describe("waitForSession", () => {
  it("resolves once the session becomes active, which is what sign-in by code needs", async () => {
    // The race behind "Invalid or missing authentication" after entering a code: the first
    // request found no session, and the session arrived a moment later.
    vi.useFakeTimers();
    const clerk = aClerk(null);
    const waiting = waitForSession(clerk, 3000);

    vi.advanceTimersByTime(200);
    clerk.activate();

    await expect(waiting).resolves.toBe(true);
    expect(clerk.listening).toBe(0);
  });

  it("resolves at once when a session is already there", async () => {
    // Clerk's first, synchronous call carries it, before `addListener` has returned.
    const clerk = aClerk({ id: "sess_1" });
    await expect(waitForSession(clerk, 3000)).resolves.toBe(true);
    expect(clerk.off).toHaveBeenCalledTimes(1);
    expect(clerk.listening).toBe(0);
  });

  it("gives up after the timeout, so a signed-out request still fails promptly", async () => {
    vi.useFakeTimers();
    const clerk = aClerk(null);
    const waiting = waitForSession(clerk, 3000);

    vi.advanceTimersByTime(3000);

    await expect(waiting).resolves.toBe(false);
    expect(clerk.listening).toBe(0);
  });
});

describe("useApiClient", () => {
  it("sends the token of a session that becomes active while the request waits", async () => {
    // The top of this file already loaded the real module; start clean so the mock applies.
    vi.resetModules();
    const clerk = aClerk(null);
    let active = false;
    const getToken = vi.fn(async () => (active ? "token-after-sign-in" : null));
    vi.doMock("@clerk/nextjs", () => ({
      useAuth: () => ({ getToken }),
      useClerk: () => clerk,
    }));
    // openapi-fetch captures `fetch` when the client is created, so stub it first.
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(
      async () => new Response("[]", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { renderHook } = await import("@testing-library/react");
    const { useApiClient } = await import("./api");
    const { result } = renderHook(() => useApiClient());

    const pending = result.current.GET("/api/v1/cases");
    // The first call found no session: the request is waiting, not sent without a header.
    await vi.waitFor(() => expect(getToken).toHaveBeenCalledTimes(1));
    expect(fetchMock).not.toHaveBeenCalled();

    active = true;
    clerk.activate();
    await pending;

    const sent = fetchMock.mock.calls[0]![0];
    expect(sent.headers.get("Authorization")).toBe("Bearer token-after-sign-in");

    vi.unstubAllGlobals();
    vi.doUnmock("@clerk/nextjs");
  });
});
