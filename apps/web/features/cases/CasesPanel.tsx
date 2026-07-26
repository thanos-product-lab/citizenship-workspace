"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useState } from "react";

import { useApiClient } from "@/lib/api";

type CaseResponse = components["schemas"]["CaseResponse"];
type LoadState = "loading" | "error" | "ready";

const STATUS_LABEL: Record<string, string> = {
  DRAFT: "Setting up",
  ACTIVE: "Active",
  ARCHIVED: "Archived",
  DELETION_PENDING: "Deletion pending",
  DELETED: "Deleted",
};

/**
 * The case list and create form. Renders all four required states explicitly:
 * loading, error (with retry), empty, and ready. Server-owned status text is
 * rendered as returned — the frontend never derives a case's lifecycle itself.
 */
export function CasesPanel() {
  const api = useApiClient();
  const [cases, setCases] = useState<CaseResponse[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  const load = useCallback(() => {
    setState("loading");
    let active = true;
    void api.GET("/api/v1/cases").then(({ data, error }) => {
      if (!active) return;
      if (error || !data) {
        setState("error");
      } else {
        setCases(data);
        setState("ready");
      }
    });
    return () => {
      active = false;
    };
  }, [api]);

  useEffect(() => load(), [load]);

  return (
    <section style={{ marginTop: "var(--cw-space-8)" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h2 style={{ fontSize: "var(--cw-text-xl)", margin: 0 }}>Your cases</h2>
      </div>

      <CreateCaseForm onCreated={(created) => setCases((prev) => [created, ...prev])} />

      <div role="status" aria-live="polite" style={{ marginTop: "var(--cw-space-6)" }}>
        {state === "loading" && (
          <p style={{ color: "var(--cw-text-muted)" }}>Loading your cases…</p>
        )}

        {state === "error" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--cw-space-3)",
              alignItems: "flex-start",
            }}
          >
            <p style={{ color: "var(--cw-status-not-satisfied)", margin: 0 }}>
              We couldn’t load your cases.
            </p>
            <button type="button" onClick={() => load()} style={buttonStyle}>
              Try again
            </button>
          </div>
        )}

        {state === "ready" && cases.length === 0 && (
          <p style={{ color: "var(--cw-text-muted)" }}>
            No cases yet. Create your first case to begin preparing your readiness case.
          </p>
        )}

        {state === "ready" && cases.length > 0 && (
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--cw-space-3)" }}>
            {cases.map((c) => (
              <li key={c.id}>
                <a
                  href={`/cases/${c.id}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "var(--cw-space-4)",
                    background: "var(--cw-surface)",
                    border: "1px solid var(--cw-border)",
                    borderRadius: "var(--cw-radius-md)",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <span style={{ fontWeight: "var(--cw-weight-medium)" }}>{c.title}</span>
                  <span style={{ fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)" }}>
                    {STATUS_LABEL[c.lifecycle_status] ?? c.lifecycle_status}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

const buttonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-accent)",
  color: "var(--cw-accent-contrast)",
  border: "none",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
};

function CreateCaseForm({ onCreated }: { onCreated: (created: CaseResponse) => void }) {
  const api = useApiClient();
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) {
      setError("Give your case a name.");
      return;
    }
    setSubmitting(true);
    setError(null);
    const { data, error: apiError } = await api.POST("/api/v1/cases", {
      body: { title: trimmed },
    });
    setSubmitting(false);
    if (apiError || !data) {
      setError("Could not create the case. Please try again.");
      return;
    }
    setTitle("");
    onCreated(data);
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{ marginTop: "var(--cw-space-4)", display: "flex", flexDirection: "column", gap: "var(--cw-space-2)" }}
    >
      <label htmlFor="new-case-title" style={{ fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)" }}>
        Case name
      </label>
      <div style={{ display: "flex", gap: "var(--cw-space-2)" }}>
        <input
          id="new-case-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. My naturalisation case"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "new-case-error" : undefined}
          maxLength={200}
          style={{
            flex: 1,
            padding: "var(--cw-space-2) var(--cw-space-3)",
            border: "1px solid var(--cw-border)",
            borderRadius: "var(--cw-radius-md)",
            background: "var(--cw-surface)",
            color: "inherit",
          }}
        />
        <button type="submit" disabled={submitting} style={buttonStyle}>
          {submitting ? "Creating…" : "Create case"}
        </button>
      </div>
      {error && (
        <p id="new-case-error" style={{ color: "var(--cw-status-not-satisfied)", margin: 0, fontSize: "var(--cw-text-sm)" }}>
          {error}
        </p>
      )}
    </form>
  );
}
