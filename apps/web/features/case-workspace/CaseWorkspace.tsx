"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { RouteOnboarding } from "@/features/onboarding/RouteOnboarding";
import { CaseOverviewPanel } from "@/features/overview/CaseOverviewPanel";
import { RequirementsList } from "@/features/requirements/RequirementsList";
import { ResidencePanel } from "@/features/timeline/ResidencePanel";
import { useApiClient } from "@/lib/api";

type Case = components["schemas"]["CaseResponse"];
type Overview = components["schemas"]["CaseOverview"];
type LoadState = "loading" | "notfound" | "error" | "ready";
type DeleteState = "idle" | "confirming" | "deleting" | "error";

/**
 * The case detail surface. Fetches the case, then branches on lifecycle:
 * DRAFT → route onboarding; ACTIVE → the workspace shell; DELETION_PENDING → a
 * pending notice. A not-found or unowned case is a single 404 state (the server
 * makes the two indistinguishable). Deletion lives here so it is available from
 * both the draft and active views.
 */
export function CaseWorkspace({ caseId }: { caseId: string }) {
  const api = useApiClient();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  // Two separate signals, because two different things go stale.
  //
  // `caseVersion` — anything that can move the *derived case phase*: a residence write,
  //   and a recalculation. The phase is derived from assessment state (ADR-0009), so a
  //   run that changes conclusions can change it, and the pill would otherwise keep
  //   showing the phase from page load.
  // `residenceVersion` — only residence writes, which mark residence results STALE
  //   server-side. A recalculation does not bump it: the list already holds the fresh
  //   results from the POST response, so refetching would be a redundant round trip.
  const [caseVersion, setCaseVersion] = useState(0);
  const [residenceVersion, setResidenceVersion] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback(
    (opts?: { focusHeadingOnDone?: boolean; quiet?: boolean }) => {
      // A refresh is `quiet`: it must not drop the workspace back to the loading state,
      // which would blank the whole page for a background refetch.
      if (!opts?.quiet) setState("loading");
      let active = true;
      void api
        .GET("/api/v1/cases/{case_id}", { params: { path: { case_id: caseId } } })
        .then(({ data, error, response }) => {
          if (!active) return;
          if (data) {
            setCaseData(data);
            setState("ready");
          } else {
            setState(response?.status === 404 ? "notfound" : "error");
          }
          if (opts?.focusHeadingOnDone) headingRef.current?.focus();
          void error;
        });
      return () => {
        active = false;
      };
    },
    [api, caseId],
  );

  useEffect(() => load(), [load]);

  useEffect(() => {
    if (caseVersion === 0) return; // the initial load above already ran
    return load({ quiet: true });
  }, [load, caseVersion]);

  // Move focus to the case heading when a user action transitions the case into
  // deletion-pending, so the confirm button that unmounts doesn't drop focus to
  // <body>. Guarded so opening an already-pending case on load doesn't steal focus.
  const prevLifecycle = useRef<string | null>(null);
  useEffect(() => {
    const lifecycle = caseData?.lifecycle_status ?? null;
    if (lifecycle === "DELETION_PENDING" && prevLifecycle.current !== null) {
      headingRef.current?.focus();
    }
    prevLifecycle.current = lifecycle;
  }, [caseData?.lifecycle_status]);

  if (state === "loading") {
    return (
      <p role="status" style={{ color: "var(--cw-text-muted)" }}>
        Loading this case…
      </p>
    );
  }

  if (state === "notfound") {
    return (
      <div>
        <h1 style={{ fontSize: "var(--cw-text-2xl)" }}>Case not found</h1>
        <p style={{ color: "var(--cw-text-muted)" }}>
          This case doesn’t exist, or it isn’t yours. <a href="/">Back to your cases</a>.
        </p>
      </div>
    );
  }

  if (state === "error" || !caseData) {
    return (
      <div role="alert">
        <p style={{ color: "var(--cw-status-not-satisfied)" }}>We couldn’t load this case.</p>
        <button type="button" onClick={() => load({ focusHeadingOnDone: true })} style={buttonStyle}>
          Try again
        </button>
      </div>
    );
  }

  const lifecycle = caseData.lifecycle_status;

  return (
    <div>
      <a href="/" style={{ color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        ← Your cases
      </a>

      {lifecycle === "DELETION_PENDING" ? (
        <section style={{ marginTop: "var(--cw-space-6)" }}>
          <h1 ref={headingRef} tabIndex={-1} style={{ fontSize: "var(--cw-text-2xl)", margin: 0 }}>
            {caseData.title}
          </h1>
          <p role="status" style={{ marginTop: "var(--cw-space-4)", color: "var(--cw-text-muted)" }}>
            This case is scheduled for deletion. It can no longer be edited.
          </p>
        </section>
      ) : (
        <>
          {lifecycle === "ACTIVE" ? (
            <WorkspaceShell
              caseData={caseData}
              headingRef={headingRef}
              onResidenceChanged={() => {
                setResidenceVersion((n) => n + 1);
                setCaseVersion((n) => n + 1);
              }}
              onAssessmentRun={() => setCaseVersion((n) => n + 1)}
              residenceVersion={residenceVersion}
            />
          ) : (
            <RouteOnboarding caseId={caseId} />
          )}
          <DeleteCaseControl
            caseId={caseId}
            onDeleted={(updated) => setCaseData(updated)}
          />
        </>
      )}
    </div>
  );
}

const PHASE_LABEL: Record<string, string> = {
  SETTING_UP: "Setting up",
  BUILDING_CASE: "Building your case",
  RESOLVING_ISSUES: "Resolving issues",
  NEARLY_PREPARED: "Nearly prepared",
  FINAL_REVIEW: "Final review",
};

function WorkspaceShell({
  caseData,
  headingRef,
  onResidenceChanged,
  onAssessmentRun,
  residenceVersion,
}: {
  caseData: Case;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  onResidenceChanged: () => void;
  /** A recalculation can change conclusions and therefore the derived phase. */
  onAssessmentRun: () => void;
  /** Bumped on every residence write; threaded into the requirements list so it
      refetches the results those writes just marked STALE. */
  residenceVersion: number;
}) {
  const [overview, setOverview] = useState<Overview | null>(null);
  return (
    <section style={{ marginTop: "var(--cw-space-6)" }}>
      {/* Header block: title + phase pill as one unit. The phase is a state, so it reads
          as a pill rather than a floating label. No roadmap prose — sections that aren't
          built simply aren't mentioned. */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--cw-space-3)", flexWrap: "wrap" }}>
        <h1 ref={headingRef} tabIndex={-1} style={{ fontSize: "var(--cw-text-2xl)", margin: 0 }}>
          {caseData.title}
        </h1>
        <span style={phasePillStyle}>
          {PHASE_LABEL[caseData.current_phase] ?? caseData.current_phase}
        </span>
      </div>

      <CaseOverview
        caseId={caseData.id}
        refreshToken={residenceVersion}
        onLoaded={setOverview}
      />
      <ResidencePanel caseId={caseData.id} onResidenceChanged={onResidenceChanged} />
      <RequirementsList
        caseId={caseData.id}
        refreshToken={residenceVersion}
        onAssessmentRun={onAssessmentRun}
        groupSummaries={overview?.groups ?? []}
      />
    </section>
  );
}

/**
 * Fetches the case overview. Kept beside the requirements list rather than folded into
 * it: the two answer different questions (where does this case stand, versus what does
 * each requirement say) and a failure in one must not blank the other.
 */
function CaseOverview({
  caseId,
  refreshToken,
  onLoaded,
}: {
  caseId: string;
  refreshToken: number;
  onLoaded: (overview: Overview) => void;
}) {
  const api = useApiClient();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    void api
      .GET("/api/v1/cases/{case_id}/overview", { params: { path: { case_id: caseId } } })
      .then(({ data, error }) => {
        if (!active) return;
        if (error || !data || !Array.isArray(data.groups)) {
          setFailed(true);
          return;
        }
        setFailed(false);
        setOverview(data);
        onLoaded(data);
      });
    return () => {
      active = false;
    };
  }, [api, caseId, refreshToken, onLoaded]);

  if (failed) {
    // Degrade quietly rather than alarm: the requirements list below carries the same
    // conclusions, so a failed summary costs context, not information.
    return null;
  }
  if (!overview) return null;
  return <CaseOverviewPanel overview={overview} />;
}

function DeleteCaseControl({
  caseId,
  onDeleted,
}: {
  caseId: string;
  onDeleted: (updated: Case) => void;
}) {
  const api = useApiClient();
  const [state, setState] = useState<DeleteState>("idle");
  const confirmRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const prevState = useRef<DeleteState>("idle");

  // Focus post-render (the target must be mounted): opening the confirm lands on
  // "Delete permanently"; cancelling back to idle returns focus to the trigger.
  useEffect(() => {
    if (state === "confirming") confirmRef.current?.focus();
    else if (prevState.current === "confirming" && state === "idle") triggerRef.current?.focus();
    prevState.current = state;
  }, [state]);

  async function doDelete() {
    setState("deleting");
    const { data } = await api.DELETE("/api/v1/cases/{case_id}", {
      params: { path: { case_id: caseId } },
    });
    if (data) {
      onDeleted(data);
      return;
    }
    setState("error");
  }

  return (
    <section
      style={{ marginTop: "var(--cw-space-8)", paddingTop: "var(--cw-space-6)", borderTop: "1px solid var(--cw-border)" }}
    >
      {state === "confirming" ? (
        <div role="group" aria-label="Confirm deletion" style={{ display: "grid", gap: "var(--cw-space-3)" }}>
          <p id="delete-warning" style={{ margin: 0 }}>
            Delete this case? This can’t be undone.
          </p>
          <div style={{ display: "flex", gap: "var(--cw-space-3)", flexWrap: "wrap" }}>
            <button
              ref={confirmRef}
              type="button"
              onClick={doDelete}
              aria-describedby="delete-warning"
              style={dangerButtonStyle}
            >
              Delete permanently
            </button>
            <button
              type="button"
              onClick={() => setState("idle")}
              style={secondaryButtonStyle}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setState("confirming")}
          disabled={state === "deleting"}
          style={secondaryButtonStyle}
        >
          {state === "deleting" ? "Deleting…" : "Delete case"}
        </button>
      )}
      {state === "error" && (
        <p role="alert" style={{ color: "var(--cw-status-not-satisfied)", marginTop: "var(--cw-space-3)" }}>
          Could not delete this case. Please try again.
        </p>
      )}
    </section>
  );
}

const phasePillStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "2px var(--cw-space-2)",
  borderRadius: "var(--cw-radius-sm)",
  background: "var(--cw-surface-sunken)",
  border: "1px solid var(--cw-border)",
  color: "var(--cw-text-muted)",
  fontSize: "var(--cw-text-xs)",
  fontWeight: "var(--cw-weight-medium)",
  whiteSpace: "nowrap",
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

const secondaryButtonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-surface)",
  color: "inherit",
  border: "1px solid var(--cw-border-strong)",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
};

const dangerButtonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-status-not-satisfied)",
  color: "var(--cw-accent-contrast)",
  border: "none",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
};
