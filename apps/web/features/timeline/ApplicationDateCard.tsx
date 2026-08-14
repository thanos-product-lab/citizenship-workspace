"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useState } from "react";

import { useApiClient } from "@/lib/api";

import { yearsFromTodayISO } from "./dates";
import { Field, buttonStyle, cardStyle, errorTextStyle, inputStyle, linkButtonStyle } from "./ui";

// Typo-guard bounds (see dates.ts). The proposed date is often future, so the window
// leans forward; both ends are generous enough never to reject a real planned date.
const MIN_DATE = yearsFromTodayISO(-20);
const MAX_DATE = yearsFromTodayISO(10);

type ProposedDate = components["schemas"]["ProposedApplicationDateResponse"];
type LoadState = "loading" | "error" | "ready";
type SaveState = "idle" | "saving" | "saved" | "conflict" | "invalid" | "error";

/**
 * Select or change the proposed application date — the date the case is assessed
 * against. No qualifying-period or presence calculation is shown here: those are the
 * deterministic rules that arrive in the next milestone. This surface only captures
 * and persists the date, with optimistic-concurrency (a stale change → reload).
 */
export function ApplicationDateCard({
  caseId,
  onResidenceChanged,
}: {
  caseId: string;
  /** Called after the date changes — which restales every residence result server-side. */
  onResidenceChanged?: () => void;
}) {
  const api = useApiClient();
  const [current, setCurrent] = useState<ProposedDate | null>(null);
  const [value, setValue] = useState("");
  const [state, setState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");

  const load = useCallback(() => {
    setState("loading");
    setSaveState("idle");
    let active = true;
    void api
      .GET("/api/v1/cases/{case_id}/application-dates", { params: { path: { case_id: caseId } } })
      .then(({ data, error }) => {
        if (!active) return;
        if (error) {
          setState("error");
          return;
        }
        if (data) {
          setCurrent(data);
          setValue(data.application_date);
        }
        setState("ready");
      });
    return () => {
      active = false;
    };
  }, [api, caseId]);

  useEffect(() => load(), [load]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!value) {
      setSaveState("invalid");
      return;
    }
    setSaveState("saving");
    const { data, response } = await api.POST("/api/v1/cases/{case_id}/application-dates/select", {
      params: { path: { case_id: caseId } },
      body: { application_date: value, expected_revision: current?.revision ?? null },
    });
    if (data) {
      setCurrent(data);
      setValue(data.application_date);
      setSaveState("saved");
      onResidenceChanged?.();
      return;
    }
    if (response?.status === 409) setSaveState("conflict");
    else if (response?.status === 422) setSaveState("invalid");
    else setSaveState("error");
  }

  return (
    <section aria-labelledby="app-date-heading" style={cardStyle}>
      <h3 id="app-date-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        Proposed application date
      </h3>
      <p style={{ marginTop: "var(--cw-space-2)", color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        The date your case is assessed against.
      </p>

      {state === "loading" && (
        <p role="status" style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-4)" }}>
          Loading…
        </p>
      )}

      {state === "error" && (
        <div role="alert" style={{ marginTop: "var(--cw-space-4)" }}>
          <p style={errorTextStyle}>We couldn’t load the application date.</p>
          <button type="button" onClick={load} style={buttonStyle}>
            Try again
          </button>
        </div>
      )}

      {state === "ready" && (
        <form onSubmit={handleSubmit} style={{ marginTop: "var(--cw-space-4)" }}>
          <Field
            id="app-date"
            label="Application date"
            error={saveState === "invalid" ? "Enter a valid date." : undefined}
          >
            <input
              id="app-date"
              type="date"
              value={value}
              min={MIN_DATE}
              max={MAX_DATE}
              className="cw-date-input"
              onChange={(e) => {
                setValue(e.target.value);
                setSaveState("idle");
              }}
              style={inputStyle}
            />
          </Field>
          <div style={{ marginTop: "var(--cw-space-4)", display: "flex", gap: "var(--cw-space-4)", alignItems: "center", flexWrap: "wrap" }}>
            <button type="submit" disabled={saveState === "saving"} style={buttonStyle}>
              {saveState === "saving" ? "Saving…" : current ? "Update date" : "Set date"}
            </button>
            <span role="status" aria-live="polite" style={{ color: "var(--cw-text-muted)" }}>
              {saveState === "saving" && "Saving…"}
              {saveState === "saved" && "Saved."}
            </span>
            {saveState === "conflict" && (
              <span role="alert" style={errorTextStyle}>
                This date changed elsewhere.{" "}
                <button type="button" onClick={load} style={linkButtonStyle}>
                  Reload the latest
                </button>
              </span>
            )}
            {saveState === "error" && (
              <span role="alert" style={errorTextStyle}>
                Something went wrong. Please try again.
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
