"use client";

import type { components } from "@cw/api-client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { RouteOnboarding } from "@/features/onboarding/RouteOnboarding";
import { CaseOverviewPanel } from "@/features/overview/CaseOverviewPanel";
import { RequirementsList } from "@/features/requirements/RequirementsList";
import { ResidencePanel } from "@/features/timeline/ResidencePanel";
import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

type Case = components["schemas"]["CaseResponse"];
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
  const client = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);

  // Keyed under the case, so a write anywhere on the page refetches this too — the case
  // carries the derived phase (ADR-0009), which moves whenever a conclusion does. There
  // are no refresh counters left: `assessmentTouched` names what went stale, and every
  // reader keyed under the case hears it, including ones added later.
  const {
    data: caseData,
    status,
    error,
    refetch,
  } = useQuery({
    queryKey: caseKeys.case(caseId),
    queryFn: async () => {
      const { data, response } = await api.GET("/api/v1/cases/{case_id}", {
        params: { path: { case_id: caseId } },
      });
      if (!data) {
        throw Object.assign(new Error("case unavailable"), { status: response?.status ?? 0 });
      }
      return data;
    },
  });

  const notFound = (error as { status?: number } | null)?.status === 404;

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

  if (status === "pending") {
    return (
      <p role="status" style={{ color: "var(--cw-text-muted)" }}>
        Loading this case…
      </p>
    );
  }

  if (notFound) {
    return (
      <div>
        <h1 style={{ fontSize: "var(--cw-text-2xl)" }}>Case not found</h1>
        <p style={{ color: "var(--cw-text-muted)" }}>
          This case doesn’t exist, or it isn’t yours. <a href="/">Back to your cases</a>.
        </p>
      </div>
    );
  }

  if (status === "error" || !caseData) {
    return (
      <div role="alert">
        <p style={{ color: "var(--cw-status-not-satisfied)" }}>We couldn’t load this case.</p>
        <button type="button" onClick={() => void refetch()} style={buttonStyle}>
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
            <WorkspaceShell caseData={caseData} headingRef={headingRef} />
          ) : (
            <RouteOnboarding caseId={caseId} />
          )}
          {/* Deletion returns the updated case, so write it straight into the cache
              rather than refetching: the server has already told us the new state. */}
          <DeleteCaseControl
            caseId={caseId}
            onDeleted={(updated) => client.setQueryData(caseKeys.case(caseId), updated)}
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
}: {
  caseData: Case;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  // The overview lives here rather than inside its panel because the group summaries it
  // returns are also rendered by the requirements list, and one fetch should serve both.
  const api = useApiClient();
  const { data: overview, status, isFetching } = useQuery({
    queryKey: caseKeys.overview(caseData.id),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/cases/{case_id}/overview", {
        params: { path: { case_id: caseData.id } },
      });
      if (!data || !Array.isArray(data.groups)) throw new Error("overview unavailable");
      return data;
    },
  });

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
          <span className="cw-visually-hidden">Case phase: </span>
          {PHASE_LABEL[caseData.current_phase] ?? caseData.current_phase}
        </span>
      </div>

      {status === "pending" ? (
        // Reserve the space so the panel does not shove already-rendered content down the
        // page once its fetch resolves.
        <div className="cw-overview__placeholder" aria-hidden="true" />
      ) : status === "error" || !overview ? (
        // The counts survive in the list below, so this is context rather than
        // information — but two things do not survive and the user must not assume they
        // were empty: the priority actions, which appear nowhere else on this screen, and
        // the case-level stale banner, the only aggregate staleness signal.
        <p className="cw-overview__unavailable">
          This summary couldn’t be loaded, so any outstanding actions aren’t shown here. The
          requirements below are current.
        </p>
      ) : (
        <CaseOverviewPanel overview={overview} updating={isFetching} />
      )}

      <ResidencePanel caseId={caseData.id} />
      <RequirementsList caseId={caseData.id} groupSummaries={overview?.groups ?? []} />
    </section>
  );
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
