"use client";

import type { components } from "@cw/api-client";
import { RequirementStatus, StatusGlyph } from "@cw/design-system";
import { useCallback, useEffect, useState } from "react";

import { useApiClient } from "@/lib/api";

import { GROUP_LABELS, groupRequirements } from "./groups";

type Requirement = components["schemas"]["RequirementSummary"];
type LoadState = "loading" | "error" | "ready";
type RunState = "idle" | "running" | "error";

/**
 * Every requirement in the case, grouped, each showing its conclusion **and** its
 * currency as two independent signals.
 *
 * The honesty rules this surface has to keep:
 *
 * - A requirement with no result reads as "Not yet assessed" with no currency badge and
 *   no summary. It is never hidden, and never shown as failing — six of the fifteen
 *   requirements have no evaluator yet, and pretending otherwise in either direction
 *   would misrepresent the case.
 * - A stale result keeps its conclusion and gains a separate notice explaining why it is
 *   no longer current. The conclusion is not restyled, greyed, or withdrawn.
 * - No count is presented as a score, a fraction, or a percentage. The group heading
 *   states how many requirements it holds, nothing more.
 */
export function RequirementsList({ caseId }: { caseId: string }) {
  const api = useApiClient();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [runState, setRunState] = useState<RunState>("idle");

  const load = useCallback(() => {
    setState("loading");
    let active = true;
    void api
      .GET("/api/v1/cases/{case_id}/requirements", { params: { path: { case_id: caseId } } })
      .then(({ data, error }) => {
        if (!active) return;
        // A malformed payload becomes the error state rather than an exception: this
        // section sits inside the case workspace, and a throw here would blank the
        // whole page instead of degrading one part of it.
        if (error || !Array.isArray(data)) {
          setState("error");
          return;
        }
        setRequirements(data);
        setState("ready");
      });
    return () => {
      active = false;
    };
  }, [api, caseId]);

  useEffect(() => load(), [load]);

  async function recalculate() {
    setRunState("running");
    const { data, error } = await api.POST("/api/v1/cases/{case_id}/assessments/recalculate", {
      params: { path: { case_id: caseId } },
    });
    if (error || !data || !Array.isArray(data.requirements)) {
      setRunState("error");
      return;
    }
    setRequirements(data.requirements);
    setRunState("idle");
  }

  const assessed = requirements.filter((r) => r.conclusion !== "NOT_YET_ASSESSED");
  const groups = groupRequirements(requirements);

  return (
    <section className="cw-section" aria-labelledby="requirements-heading">
      <div className="cw-section__header">
        <div>
          <h2 id="requirements-heading">Requirements</h2>
          <p className="cw-section__note">
            Each requirement shows what was concluded and whether that conclusion is still
            current. Open a requirement to see the facts and rule behind it.
          </p>
        </div>
        {state === "ready" && assessed.length > 0 ? (
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => void recalculate()}
            disabled={runState === "running"}
          >
            {runState === "running" ? "Recalculating…" : "Recalculate"}
          </button>
        ) : null}
      </div>

      {/* Announce the outcome of a recalculation to screen-reader users, who get no
          visual cue from badges changing in place. */}
      <p aria-live="polite" className="cw-visually-hidden">
        {runState === "running" ? "Recalculating requirements." : ""}
      </p>

      {state === "loading" ? (
        <p role="status" style={{ color: "var(--cw-text-muted)" }}>
          Loading requirements…
        </p>
      ) : null}

      {state === "error" ? (
        <div role="alert" className="cw-empty">
          <p>We couldn’t load the requirements for this case.</p>
          <div className="cw-empty__actions">
            <button type="button" className="cw-button cw-button--secondary" onClick={() => load()}>
              Try again
            </button>
          </div>
        </div>
      ) : null}

      {state === "ready" && requirements.length === 0 ? (
        <div className="cw-empty">
          <p>No requirements are catalogued for this route yet.</p>
        </div>
      ) : null}

      {state === "ready" && requirements.length > 0 && assessed.length === 0 ? (
        <div className="cw-empty">
          <p>
            Nothing has been assessed yet. Once you’ve set an application date, run an
            assessment to see where this case stands.
          </p>
          <div className="cw-empty__actions">
            <button
              type="button"
              className="cw-button"
              onClick={() => void recalculate()}
              disabled={runState === "running"}
            >
              {runState === "running" ? "Assessing…" : "Run assessment"}
            </button>
          </div>
        </div>
      ) : null}

      {runState === "error" ? (
        <p role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
          We couldn’t recalculate this case. Nothing has changed — please try again.
        </p>
      ) : null}

      {state === "ready" && assessed.length > 0 ? (
        <div className="cw-requirement-groups">
          {groups.map((group) => (
            <section
              key={group.key}
              className="cw-requirement-group"
              aria-labelledby={`group-${group.key}`}
            >
              <h3 id={`group-${group.key}`}>{GROUP_LABELS[group.key] ?? group.key}</h3>
              <p className="cw-requirement-group__count">
                {group.items.length === 1 ? "1 requirement" : `${group.items.length} requirements`}
              </p>
              <ul className="cw-requirement-list">
                {group.items.map((requirement) => (
                  <li key={requirement.requirement_key}>
                    <RequirementRow requirement={requirement} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function RequirementRow({ requirement }: { requirement: Requirement }) {
  const unassessed = requirement.conclusion === "NOT_YET_ASSESSED";
  return (
    <div className="cw-requirement-row">
      <div className="cw-requirement-row__main">
        <h4 className="cw-requirement-row__title">{requirement.title}</h4>
        <p className="cw-requirement-row__summary">
          {requirement.summary?.text ??
            (unassessed
              ? "This requirement hasn’t been assessed yet."
              : "No plain-language summary is available for this result.")}
        </p>
        {requirement.stale ? (
          <p className="cw-stale-notice">
            <StatusGlyph name="clock" size={16} />
            <span>
              {requirement.stale.reason ?? "An input changed after this was worked out."} This
              conclusion still stands, but it needs recalculating.
            </span>
          </p>
        ) : null}
      </div>
      <RequirementStatus
        conclusion={requirement.conclusion}
        currency={requirement.currency}
        size="sm"
      />
    </div>
  );
}
