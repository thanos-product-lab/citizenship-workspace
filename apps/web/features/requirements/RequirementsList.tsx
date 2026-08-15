"use client";

import type { components } from "@cw/api-client";
import { RequirementStatus, StaleAssessmentNotice } from "@cw/design-system";
import { useCallback, useEffect, useRef, useState } from "react";

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
 * - A stale result keeps its conclusion and gains a separate notice saying the
 *   conclusion **has not been rechecked**. The notice must never claim the conclusion
 *   still holds: that is precisely what a stale result cannot tell us.
 * - No count is presented as a score, a fraction, or a percentage.
 *
 * `refreshToken` is how the parent tells this list that a residence input changed. Those
 * writes mark residence results STALE server-side in the same transaction, so without a
 * refetch this list would keep rendering conclusions the API has already flagged.
 */
export function RequirementsList({
  caseId,
  refreshToken = 0,
  onAssessmentRun,
}: {
  caseId: string;
  refreshToken?: number;
  /** Called after a recalculation lands. The case phase is derived from assessment
      state (ADR-0009), so a run that changes conclusions can move it — without this the
      phase pill keeps showing whatever it was at page load. */
  onAssessmentRun?: () => void;
}) {
  const api = useApiClient();
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [runState, setRunState] = useState<RunState>("idle");
  const [announcement, setAnnouncement] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const returnFocusToHeading = useRef(false);

  const load = useCallback(
    (opts?: { focusHeadingOnDone?: boolean }) => {
      setState("loading");
      if (opts?.focusHeadingOnDone) returnFocusToHeading.current = true;
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
    },
    [api, caseId],
  );

  // Refetches on mount and whenever the parent signals a residence input changed.
  useEffect(() => load(), [load, refreshToken]);

  // A button that unmounts takes the keyboard focus with it, dropping the user to
  // <body>. Park focus on the section heading instead, post-render so the target exists.
  useEffect(() => {
    if (state !== "loading" && returnFocusToHeading.current) {
      returnFocusToHeading.current = false;
      headingRef.current?.focus();
    }
  }, [state]);

  async function recalculate() {
    setRunState("running");
    setAnnouncement("Recalculating requirements.");
    const { data, error } = await api.POST("/api/v1/cases/{case_id}/assessments/recalculate", {
      params: { path: { case_id: caseId } },
    });
    if (error || !data || !Array.isArray(data.requirements)) {
      setRunState("error");
      setAnnouncement("Recalculation did not complete.");
      return;
    }
    setRequirements(data.requirements);
    setRunState("idle");
    onAssessmentRun?.();
    // Emptying a live region announces nothing, so the completion has to be its own
    // message: badges change in place, which gives a screen-reader user no other cue.
    const current = data.requirements.filter((r) => r.conclusion !== "NOT_YET_ASSESSED").length;
    setAnnouncement(
      `Recalculation finished. ${current} ${current === 1 ? "requirement" : "requirements"} assessed.`,
    );
  }

  // "Has a result" is a question about currency, not conclusion: a *stored*
  // NOT_YET_ASSESSED result is a real result with a real currency, and filtering on the
  // conclusion would hide it — including when it is STALE.
  const withResults = requirements.filter((r) => r.currency !== null);
  const groups = groupRequirements(requirements);
  const busy = runState === "running";

  return (
    <section className="cw-section" aria-labelledby="requirements-heading">
      <div className="cw-section__header">
        <div>
          <h2 id="requirements-heading" ref={headingRef} tabIndex={-1}>
            Requirements
          </h2>
          <p className="cw-section__note">
            Each requirement shows what was concluded and whether that conclusion is still
            current. Open a requirement to see the facts and rule behind it.
          </p>
        </div>
        {state === "ready" && withResults.length > 0 ? (
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => void (busy ? undefined : recalculate())}
            // aria-disabled, not disabled: a focused button that becomes `disabled` is
            // blurred by the browser, silently dropping focus mid-operation.
            aria-disabled={busy}
          >
            {busy ? "Recalculating…" : "Recalculate"}
          </button>
        ) : null}
      </div>

      {/* Mounted unconditionally: a live region whose container and text appear in the
          same commit is frequently missed by NVDA and JAWS. */}
      <p aria-live="polite" className="cw-visually-hidden">
        {state === "loading" ? "Loading requirements." : announcement}
      </p>

      {state === "loading" ? (
        <p style={{ color: "var(--cw-text-muted)" }}>Loading requirements…</p>
      ) : null}

      {state === "error" ? (
        <div role="alert" className="cw-empty">
          <p>We couldn’t load the requirements for this case.</p>
          <div className="cw-empty__actions">
            <button
              type="button"
              className="cw-button cw-button--secondary"
              onClick={() => load({ focusHeadingOnDone: true })}
            >
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

      {state === "ready" && requirements.length > 0 && withResults.length === 0 ? (
        <div className="cw-empty">
          <p>
            Nothing has been assessed yet. Once you’ve set an application date, run an
            assessment to see where this case stands.
          </p>
          <div className="cw-empty__actions">
            <button
              type="button"
              className="cw-button"
              onClick={() => void (busy ? undefined : recalculate())}
              aria-disabled={busy}
            >
              {busy ? "Assessing…" : "Run assessment"}
            </button>
          </div>
        </div>
      ) : null}

      {runState === "error" ? (
        <p role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
          {/* Deliberately not "nothing has changed": a timeout or a dropped response
              after commit would make that false, and the user would be told the case is
              unchanged while looking at a list that is out of date. */}
          We couldn’t confirm whether that recalculation ran. Reload the page to see the
          current state.
        </p>
      ) : null}

      {state === "ready" && withResults.length > 0 ? (
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
                    <RequirementRow requirement={requirement} caseId={caseId} />
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

function RequirementRow({
  requirement,
  caseId,
}: {
  requirement: Requirement;
  caseId: string;
}) {
  const unassessed = requirement.conclusion === "NOT_YET_ASSESSED";
  return (
    <div className="cw-requirement-row">
      <div className="cw-requirement-row__main">
        <h4 className="cw-requirement-row__title">
          {/* The whole row is not a link: the summary beneath it is prose a screen-reader
              user should be able to read without it being announced as link text. */}
          <a
            className="cw-requirement-row__link"
            href={`/cases/${caseId}/requirements/${encodeURIComponent(requirement.requirement_key)}`}
          >
            {requirement.title}
          </a>
        </h4>
        <p className="cw-requirement-row__summary">
          {requirement.summary?.text ??
            (unassessed
              ? "This requirement hasn’t been assessed yet."
              : "No plain-language summary is available for this result.")}
        </p>
        {requirement.stale ? <StaleAssessmentNotice reason={requirement.stale.reason} /> : null}
      </div>
      <RequirementStatus
        conclusion={requirement.conclusion}
        currency={requirement.currency}
        size="sm"
      />
    </div>
  );
}
