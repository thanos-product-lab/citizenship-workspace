"use client";

import type { components } from "@cw/api-client";
import { useEffect, useState } from "react";

import { useApiClient } from "@/lib/api";

type CurrentUser = components["schemas"]["CurrentUser"];
type LoadState = "loading" | "error" | "ready";

export function CurrentUserPanel() {
  const api = useApiClient();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    void api.GET("/api/v1/me").then(({ data, error }) => {
      if (!active) return;
      if (error || !data) {
        setState("error");
      } else {
        setUser(data);
        setState("ready");
      }
    });
    return () => {
      active = false;
    };
  }, [api]);

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        marginTop: "var(--cw-space-6)",
        padding: "var(--cw-space-4)",
        background: "var(--cw-surface)",
        border: "1px solid var(--cw-border)",
        borderRadius: "var(--cw-radius-md)",
      }}
    >
      {state === "loading" && (
        <span style={{ color: "var(--cw-text-muted)" }}>Loading your account…</span>
      )}
      {state === "error" && (
        <span style={{ color: "var(--cw-status-not-satisfied)" }}>
          Could not load your account.
        </span>
      )}
      {state === "ready" && user && (
        <span>
          Signed in as{" "}
          <span style={{ fontFamily: "var(--cw-font-mono)" }}>{user.email ?? user.user_id}</span>
        </span>
      )}
    </div>
  );
}
