"use client";

import type { components } from "@cw/api-client";
import { cloneElement, isValidElement, useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement, ReactNode } from "react";

import { useApiClient } from "@/lib/api";

type RouteProfile = components["schemas"]["RouteProfileResponse"];
type RouteSupport = components["schemas"]["RouteSupportResponse"];
type StatusType = components["schemas"]["StatusType"];
type LoadState = "loading" | "error" | "ready";
type SaveState = "idle" | "saving" | "saved" | "conflict" | "error";
type ConfirmState = "idle" | "confirming" | "incomplete" | "conflict" | "error";

const STATUS_OPTIONS: { value: StatusType; label: string }[] = [
  { value: "ILR", label: "Indefinite leave to remain (ILR)" },
  { value: "ILE", label: "Indefinite leave to enter" },
  { value: "EU_SETTLED_STATUS", label: "EU settled status" },
  { value: "OTHER", label: "Something else" },
  { value: "UNKNOWN", label: "I’m not sure" },
];

const FIELD_LABEL: Record<string, string> = {
  date_of_birth: "date of birth",
  status_type: "immigration status",
  status_granted_on: "when your status was granted",
  married_to_british_citizen: "the spouse-route question",
  may_already_be_british: "the British-citizen question",
};

// Missing-answer key → the control's DOM id, so a 422 can flag and focus the field.
const FIELD_ID: Record<string, string> = {
  date_of_birth: "dob",
  status_type: "status",
  status_granted_on: "granted",
  married_to_british_citizen: "spouse",
  may_already_be_british: "already-british",
};

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
 * Route-scope onboarding for one case: capture answers, save/resume, and confirm.
 * Confirming saves the on-screen answers first (so the confirmed version matches
 * what the user sees) then asks the server for the route-support decision, which
 * is rendered as a supported / not-supported / needs-review outcome. The server
 * owns the decision; this component only displays what it returns.
 */
export function RouteOnboarding({ caseId }: { caseId: string }) {
  const api = useApiClient();
  const [answers, setAnswers] = useState<FormAnswers>(EMPTY);
  const [revision, setRevision] = useState<number | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [confirmState, setConfirmState] = useState<ConfirmState>("idle");
  const [missing, setMissing] = useState<string[]>([]);
  const [decision, setDecision] = useState<RouteSupport | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const outcomeRef = useRef<HTMLHeadingElement>(null);

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

  // Move focus to the outcome once a decision arrives, so it is announced and a
  // keyboard user lands on the result rather than staying on the confirm button.
  useEffect(() => {
    if (decision) outcomeRef.current?.focus();
  }, [decision]);

  function answersBody() {
    return {
      date_of_birth: answers.date_of_birth || null,
      status_type: answers.status_type || null,
      status_granted_on: answers.status_granted_on || null,
      married_to_british_citizen: fromTri(answers.married_to_british_citizen),
      may_already_be_british: fromTri(answers.may_already_be_british),
    };
  }

  async function save(): Promise<{ revision: number } | null> {
    const { data, response } = await api.PUT("/api/v1/cases/{case_id}/route-profile", {
      params: { path: { case_id: caseId } },
      body: { ...answersBody(), expected_revision: revision },
    });
    if (data) {
      setRevision(data.revision);
      return { revision: data.revision };
    }
    setSaveState(response?.status === 409 ? "conflict" : "error");
    return null;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaveState("saving");
    if (await save()) setSaveState("saved");
  }

  async function handleConfirm() {
    setConfirmState("confirming");
    // Save what's on screen first, so the confirmed version matches the form.
    const saved = await save();
    if (!saved) {
      setConfirmState("idle");
      return;
    }
    const { data, error, response } = await api.POST(
      "/api/v1/cases/{case_id}/route-profile/confirm",
      { params: { path: { case_id: caseId } }, body: { expected_revision: saved.revision } },
    );
    if (data) {
      setDecision(data);
      setConfirmState("idle");
      // A non-supported case stays a DRAFT; refresh the revision so the user can
      // edit and re-confirm. (A supported case is now active — the form is hidden.)
      if (data.support_status !== "SUPPORTED") load();
      return;
    }
    if (response?.status === 422) {
      const body = error as { missing_fields?: string[] } | undefined;
      const fields = body?.missing_fields ?? [];
      setMissing(fields);
      setConfirmState("incomplete");
      // Send the user straight to the first field that needs an answer.
      const firstKey = fields[0];
      const firstId = firstKey ? FIELD_ID[firstKey] : undefined;
      if (firstId) queueMicrotask(() => document.getElementById(firstId)?.focus());
      return;
    }
    setConfirmState(response?.status === 409 ? "conflict" : "error");
  }

  function update<K extends keyof FormAnswers>(key: K, value: FormAnswers[K]) {
    setAnswers((prev) => ({ ...prev, [key]: value }));
    setSaveState("idle");
    setConfirmState("idle");
  }

  const today = todayLocal();
  const supported = decision?.support_status === "SUPPORTED";
  const showForm = state === "ready" && !supported;
  // A field is flagged invalid only while an unresolved "incomplete" confirm names
  // it; editing any field resets confirmState to idle, clearing the flags.
  const invalid = (key: string): true | undefined =>
    confirmState === "incomplete" && missing.includes(key) ? true : undefined;

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

      {decision && <OutcomePanel decision={decision} headingRef={outcomeRef} />}

      {showForm && (
        <form onSubmit={handleSubmit} style={{ marginTop: "var(--cw-space-6)" }}>
          <div style={{ display: "grid", gap: "var(--cw-space-6)" }}>
            <Field id="dob" label="Date of birth">
              <input
                id="dob"
                type="date"
                value={answers.date_of_birth}
                max={today}
                aria-invalid={invalid("date_of_birth")}
                onChange={(e) => update("date_of_birth", e.target.value)}
                style={inputStyle}
              />
            </Field>

            <Field id="status" label="Your current immigration status">
              <select
                id="status"
                value={answers.status_type}
                aria-invalid={invalid("status_type")}
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
                aria-invalid={invalid("status_granted_on")}
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
                aria-invalid={invalid("married_to_british_citizen")}
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
                aria-invalid={invalid("may_already_be_british")}
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
            <button type="submit" disabled={saveState === "saving"} style={secondaryButtonStyle}>
              {saveState === "saving" ? "Saving…" : "Save answers"}
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={confirmState === "confirming"}
              style={buttonStyle}
            >
              {confirmState === "confirming" ? "Checking…" : "Confirm route"}
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
            {(saveState === "error" || confirmState === "error") && (
              <span role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
                Something went wrong. Please try again.
              </span>
            )}
            {confirmState === "conflict" && (
              <span role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
                These answers changed elsewhere; reload before confirming.
              </span>
            )}
            {confirmState === "incomplete" && (
              <span role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
                Please answer {missing.map((m) => FIELD_LABEL[m] ?? m).join(", ")} before confirming.
              </span>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

type Tone = "supported" | "unsupported" | "review";

interface OutcomeView {
  tone: Tone;
  label: string;
  heading: string;
  body: string;
}

const TONE_SURFACE: Record<Tone, string> = {
  supported: "var(--cw-status-supported-surface)",
  unsupported: "var(--cw-status-not-satisfied-surface)",
  review: "var(--cw-status-requires-judgement-surface)",
};

function outcomeView(decision: RouteSupport): OutcomeView {
  switch (decision.summary_code) {
    case "ROUTE_STANDARD_CONFIRMED":
      return {
        tone: "supported",
        label: "Supported",
        heading: "Your case is set up",
        body: "This workspace supports the standard five-year route. You can start building your case.",
      };
    case "ROUTE_SPOUSE_UNSUPPORTED":
      return {
        tone: "unsupported",
        label: "Not supported",
        heading: "This prototype doesn’t cover the spouse route",
        body: "Applying as the spouse or civil partner of a British citizen follows a different route that this prototype doesn’t handle.",
      };
    case "ROUTE_MAY_BE_BRITISH":
      return {
        tone: "review",
        label: "Needs review",
        heading: "You may already be a British citizen",
        body: "If you are already British you may not need to naturalise at all. This needs a person to check before going further.",
      };
    default: {
      // ROUTE_PREREQUISITES_UNMET — distinguish age from status for a useful message.
      const adult = decision.requirements.find((r) => r.requirement_key === "route.adult_applicant");
      if (adult && adult.conclusion !== "SUPPORTED") {
        return {
          tone: "unsupported",
          label: "Not supported",
          heading: "This route is for adult applicants",
          body: "Naturalisation is for applicants aged 18 or over. Under-18s follow a registration route this prototype doesn’t cover.",
        };
      }
      return {
        tone: "unsupported",
        label: "Not supported",
        heading: "Your status isn’t supported here",
        body: "The standard route needs indefinite leave to remain, indefinite leave to enter, or EU settled status.",
      };
    }
  }
}

function OutcomePanel({
  decision,
  headingRef,
}: {
  decision: RouteSupport;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const view = outcomeView(decision);
  return (
    <section
      aria-labelledby="outcome-heading"
      style={{
        marginTop: "var(--cw-space-6)",
        padding: "var(--cw-space-5)",
        background: TONE_SURFACE[view.tone],
        border: "1px solid var(--cw-border)",
        borderRadius: "var(--cw-radius-md)",
      }}
    >
      {/* Text label carries the status — never colour alone — and is folded into
          the heading's accessible name so it's spoken when focus lands here. */}
      <p
        id="outcome-label"
        style={{ margin: 0, fontSize: "var(--cw-text-sm)", fontWeight: "var(--cw-weight-semibold)" }}
      >
        {view.label}
      </p>
      <h2
        id="outcome-heading"
        ref={headingRef}
        tabIndex={-1}
        aria-describedby="outcome-label"
        style={{ margin: "var(--cw-space-2) 0 0", fontSize: "var(--cw-text-xl)" }}
      >
        {view.heading}
      </h2>
      <p style={{ margin: "var(--cw-space-2) 0 0" }}>{view.body}</p>
      {view.tone === "supported" && (
        <a href="/" style={{ display: "inline-block", marginTop: "var(--cw-space-4)", ...buttonStyle }}>
          Go to your workspace
        </a>
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
  "aria-invalid"?: true | undefined;
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
  textDecoration: "none",
};

const secondaryButtonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-surface)",
  color: "inherit",
  border: "1px solid var(--cw-border-strong)",
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
