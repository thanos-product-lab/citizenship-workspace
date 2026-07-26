"use client";

import type { components } from "@cw/api-client";
import { cloneElement, isValidElement, useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import { useApiClient } from "@/lib/api";

type RouteProfile = components["schemas"]["RouteProfileResponse"];
type StatusType = components["schemas"]["StatusType"];
type LoadState = "loading" | "error" | "ready";
type SaveState = "idle" | "saving" | "saved" | "conflict" | "error";

const STATUS_OPTIONS: { value: StatusType; label: string }[] = [
  { value: "ILR", label: "Indefinite leave to remain (ILR)" },
  { value: "ILE", label: "Indefinite leave to enter" },
  { value: "EU_SETTLED_STATUS", label: "EU settled status" },
  { value: "OTHER", label: "Something else" },
  { value: "UNKNOWN", label: "I’m not sure" },
];

// Tri-state yes/no: "" is unanswered, distinct from a deliberate "No".
type TriState = "" | "yes" | "no";
const toTri = (v: boolean | null | undefined): TriState => (v == null ? "" : v ? "yes" : "no");
const fromTri = (v: TriState): boolean | null => (v === "" ? null : v === "yes");

/** Today's date as YYYY-MM-DD in the viewer's local timezone (not UTC). */
function todayLocal(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

interface FormAnswers {
  date_of_birth: string;
  status_type: StatusType | "";
  status_granted_on: string;
  married_to_british_citizen: TriState;
  may_already_be_british: TriState;
}

const EMPTY: FormAnswers = {
  date_of_birth: "",
  status_type: "",
  status_granted_on: "",
  married_to_british_citizen: "",
  may_already_be_british: "",
};

function fromProfile(p: RouteProfile): FormAnswers {
  return {
    date_of_birth: p.date_of_birth ?? "",
    status_type: (p.status_type as StatusType | null) ?? "",
    status_granted_on: p.status_granted_on ?? "",
    married_to_british_citizen: toTri(p.married_to_british_citizen),
    may_already_be_british: toTri(p.may_already_be_british),
  };
}

/**
 * Route-scope onboarding for one case. Loads any saved draft so a returning user
 * resumes where they left off, then saves the whole answer set on submit. No
 * support outcome is shown here — that arrives with the confirm step in a later
 * slice; this slice only captures and resumes answers.
 *
 * Accessibility (matching the Slice 1 patterns): the heading is present in every
 * state so there is always something to land on, and focus moves to it after a
 * user-initiated retry/reload; save status lives in a persistent polite live
 * region (saving/saved) with conflict/error as assertive alerts.
 */
export function RouteOnboarding({ caseId }: { caseId: string }) {
  const api = useApiClient();
  const [answers, setAnswers] = useState<FormAnswers>(EMPTY);
  const [revision, setRevision] = useState<number | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback(
    (opts?: { focusHeadingOnDone?: boolean }) => {
      setState("loading");
      setSaveState("idle"); // a reload clears any stale "saved"/"conflict" message
      let active = true;
      void api
        .GET("/api/v1/cases/{case_id}/route-profile", { params: { path: { case_id: caseId } } })
        .then(({ data, error }) => {
          if (!active) return;
          if (error) {
            setState("error");
          } else {
            if (data) {
              setAnswers(fromProfile(data));
              setRevision(data.revision);
            }
            setState("ready");
          }
          if (opts?.focusHeadingOnDone) headingRef.current?.focus();
        });
      return () => {
        active = false;
      };
    },
    [api, caseId],
  );

  useEffect(() => load(), [load]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaveState("saving");
    const { data, error, response } = await api.PUT("/api/v1/cases/{case_id}/route-profile", {
      params: { path: { case_id: caseId } },
      body: {
        date_of_birth: answers.date_of_birth || null,
        status_type: answers.status_type || null,
        status_granted_on: answers.status_granted_on || null,
        married_to_british_citizen: fromTri(answers.married_to_british_citizen),
        may_already_be_british: fromTri(answers.may_already_be_british),
        expected_revision: revision,
      },
    });
    if (data) {
      setRevision(data.revision);
      setSaveState("saved");
      return;
    }
    setSaveState(response?.status === 409 ? "conflict" : "error");
    void error;
  }

  function update<K extends keyof FormAnswers>(key: K, value: FormAnswers[K]) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
    setSaveState("idle");
  }

  const today = todayLocal();

  return (
    <section style={{ marginTop: "var(--cw-space-6)" }}>
      <h1 ref={headingRef} tabIndex={-1} style={{ fontSize: "var(--cw-text-2xl)", margin: 0 }}>
        Your route
      </h1>
      <p style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-2)" }}>
        A few questions confirm this workspace fits your application. You can save and return
        at any time.
      </p>

      {state === "loading" && (
        <p role="status" style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-6)" }}>
          Loading your answers…
        </p>
      )}

      {state === "error" && (
        <div role="alert" style={{ marginTop: "var(--cw-space-6)" }}>
          <p style={{ color: "var(--cw-status-not-satisfied)" }}>We couldn’t load this case.</p>
          <button type="button" onClick={() => load({ focusHeadingOnDone: true })} style={buttonStyle}>
            Try again
          </button>
        </div>
      )}

      {state === "ready" && (
        <form onSubmit={handleSubmit} style={{ marginTop: "var(--cw-space-6)" }}>
          <div style={{ display: "grid", gap: "var(--cw-space-6)" }}>
            <Field id="dob" label="Date of birth">
              <input
                id="dob"
                type="date"
                value={answers.date_of_birth}
                max={today}
                onChange={(e) => update("date_of_birth", e.target.value)}
                style={inputStyle}
              />
            </Field>

            <Field id="status" label="Your current immigration status">
              <select
                id="status"
                value={answers.status_type}
                onChange={(e) => update("status_type", e.target.value as StatusType | "")}
                style={inputStyle}
              >
                <option value="">Select…</option>
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field id="granted" label="When was that status granted?">
              <input
                id="granted"
                type="date"
                value={answers.status_granted_on}
                max={today}
                onChange={(e) => update("status_granted_on", e.target.value)}
                style={inputStyle}
              />
            </Field>

            <Field
              id="spouse"
              label="Are you applying as the spouse or civil partner of a British citizen?"
              hint="The prototype currently supports the standard five-year route, not the spouse route."
            >
              <YesNoSelect
                id="spouse"
                value={answers.married_to_british_citizen}
                onChange={(v) => update("married_to_british_citizen", v)}
              />
            </Field>

            <Field
              id="already-british"
              label="Is there any chance you are already a British citizen?"
              hint="For example, through a parent. If so, you may not need to naturalise at all."
            >
              <YesNoSelect
                id="already-british"
                value={answers.may_already_be_british}
                onChange={(v) => update("may_already_be_british", v)}
              />
            </Field>
          </div>

          <div
            style={{
              marginTop: "var(--cw-space-8)",
              display: "flex",
              alignItems: "center",
              gap: "var(--cw-space-4)",
              flexWrap: "wrap",
            }}
          >
            <button type="submit" disabled={saveState === "saving"} style={buttonStyle}>
              {saveState === "saving" ? "Saving…" : "Save answers"}
            </button>
            {/* Persistent polite region: swaps text rather than mounting on demand. */}
            <span role="status" aria-live="polite" style={{ color: "var(--cw-text-muted)" }}>
              {saveState === "saving" && "Saving…"}
              {saveState === "saved" && "Saved."}
            </span>
            {saveState === "conflict" && (
              <span role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
                These answers changed elsewhere.{" "}
                <button type="button" onClick={() => load({ focusHeadingOnDone: true })} style={linkButtonStyle}>
                  Reload the latest
                </button>
              </span>
            )}
            {saveState === "error" && (
              <span role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
                Could not save. Please try again.
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

/**
 * Label + optional hint + control. Field owns the hint↔control association: when a
 * hint is present it stamps `aria-describedby` onto the single child control, so a
 * hint is announced regardless of which control type it wraps and a control without
 * a hint never carries a dangling reference.
 */
function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const control =
    hintId && isValidElement(children)
      ? cloneElement(children as ReactElement<{ "aria-describedby"?: string }>, {
          "aria-describedby": hintId,
        })
      : children;
  return (
    <div style={{ display: "grid", gap: "var(--cw-space-2)" }}>
      <label htmlFor={id} style={{ fontWeight: "var(--cw-weight-medium)" }}>
        {label}
      </label>
      {hint && (
        <p id={hintId} style={{ margin: 0, fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)" }}>
          {hint}
        </p>
      )}
      {control}
    </div>
  );
}

function YesNoSelect({
  id,
  value,
  onChange,
  ...rest
}: {
  id: string;
  value: TriState;
  onChange: (v: TriState) => void;
  "aria-describedby"?: string;
}) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value as TriState)}
      style={inputStyle}
      {...rest}
    >
      <option value="">Select…</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </select>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-3)",
  border: "1px solid var(--cw-border)",
  borderRadius: "var(--cw-radius-md)",
  background: "var(--cw-surface)",
  color: "inherit",
  maxWidth: "24rem",
};

const buttonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-accent)",
  color: "var(--cw-accent-contrast)",
  border: "none",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
};

const linkButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  padding: 0,
  color: "inherit",
  textDecoration: "underline",
  cursor: "pointer",
  font: "inherit",
};
