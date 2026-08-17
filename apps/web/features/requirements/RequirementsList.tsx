"use client";

import type { components } from "@cw/api-client";
import { RequirementStatus, StaleAssessmentNotice, StatusGlyph } from "@cw/design-system";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useApiClient } from "@/lib/api";
import { assessmentTouched, caseKeys } from "@/lib/queries";

import { GROUP_LABELS, groupRequirements } from "./groups";

type Requirement = components["schemas"]["RequirementSummary"];
type GroupSummary = components["schemas"]["GroupSummaryView"];

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
 * Invalidation is the cache's job, not a prop's: a recalculation here calls
 * `assessmentTouched`, and any write elsewhere on the page does the same, so this list
 * refetches without the parent knowing it exists.
 */
export function RequirementsList({
  caseId,
  groupSummaries = [],
}: {
  caseId: string;
  /** Per-group counts and currency from the overview projection (ADR-0010). A group's
      currency inherits its weakest member, so a heading can show the group as stale even
      when the rows beneath it each look individually fine. */
  groupSummaries?: GroupSummary[];
}) {
  const api = useApiClient();
  const client = useQueryClient();
  const [announcement, setAnnouncement] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);
  const returnFocusToHeading = useRef(false);

  const { data, status, refetch, isFetching } = useQuery({
    queryKey: caseKeys.requirements(caseId),
    queryFn: async () => {
      const { data } = await api.GET("/api/v1/cases/{case_id}/requirements", {
        params: { path: { case_id: caseId } },
      });
      // A malformed payload is an error rather than an exception: this section sits inside
      // the case workspace, and a throw would blank the page instead of degrading one part.
      if (!Array.isArray(data)) throw new Error("requirements unavailable");
      return data;
    },
  });

  const recalculate = useMutation({
    mutationFn: async () => {
      const { data } = await api.POST("/api/v1/cases/{case_id}/assessments/recalculate", {
        params: { path: { case_id: caseId } },
      });
      if (!data || !Array.isArray(data.requirements)) throw new Error("recalculation failed");
      return data;
    },
    onSuccess: async (data) => {
      // One statement — "this case's assessment state moved" — reaches every reader,
      // including the overview and the case's derived phase. Previously each was wired by
      // hand and one was missed three separate times.
      await assessmentTouched(client, caseId);
      // Emptying a live region announces nothing, so the completion has to be its own
      // message: badges change in place, which gives a screen-reader user no other cue.
      const current = data.requirements.filter((r) => r.conclusion !== "NOT_YET_ASSESSED").length;
      setAnnouncement(
        `Recalculation finished. ${current} ${current === 1 ? "requirement" : "requirements"} assessed.`,
      );
    },
    onError: () => setAnnouncement("Recalculation did not complete."),
  });

  const requirements = data ?? [];

  // A button that unmounts takes the keyboard focus with it, dropping the user to
  // <body>. Park focus on the section heading instead, post-render so the target exists.
  useEffect(() => {
    if (status !== "pending" && returnFocusToHeading.current) {
      returnFocusToHeading.current = false;
      headingRef.current?.focus();
    }
  }, [status]);

  // "Has a result" is a question about currency, not conclusion: a *stored*
  // NOT_YET_ASSESSED result is a real result with a real currency, and filtering on the
  // conclusion would hide it — including when it is STALE.
  const withResults = requirements.filter((r) => r.currency !== null);
  const groups = groupRequirements(requirements);
  // Busy spans the whole operation, not just the POST. The mutation resolves, then
  // invalidation triggers a refetch — and during that window the rows below still show
  // the previous run's conclusions. Releasing the button at the halfway point would invite
  // a second click against numbers that are already being replaced.
  const busy = recalculate.isPending || (isFetching && status === "success");

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
        {status === "success" && withResults.length > 0 ? (
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => (busy ? undefined : recalculate.mutate())}
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
        {status === "pending" ? "Loading requirements." : announcement}
      </p>

      {/* The rows below are the previous run's until the refetch lands. Saying so is the
          difference between a slow update and a screen quietly showing superseded
          conclusions (UI/UX §16: recalculation in progress is a state to design). */}
      {busy && status === "success" ? (
        <p className="cw-updating">
          <StatusGlyph name="clock" size={14} />
          <span>Updating — the conclusions below are from the previous run.</span>
        </p>
      ) : null}

      {status === "pending" ? (
        <p style={{ color: "var(--cw-text-muted)" }}>Loading requirements…</p>
      ) : null}

      {status === "error" ? (
        <div role="alert" className="cw-empty">
          <p>We couldn’t load the requirements for this case.</p>
          <div className="cw-empty__actions">
            <button
              type="button"
              className="cw-button cw-button--secondary"
              onClick={() => {
                returnFocusToHeading.current = true;
                void refetch();
              }}
            >
              Try again
            </button>
          </div>
        </div>
      ) : null}

      {status === "success" && requirements.length === 0 ? (
        <div className="cw-empty">
          <p>No requirements are catalogued for this route yet.</p>
        </div>
      ) : null}

      {status === "success" && requirements.length > 0 && withResults.length === 0 ? (
        <div className="cw-empty">
          <p>
            Nothing has been assessed yet. Once you’ve set an application date, run an
            assessment to see where this case stands.
          </p>
          <div className="cw-empty__actions">
            <button
              type="button"
              className="cw-button"
              onClick={() => (busy ? undefined : recalculate.mutate())}
              aria-disabled={busy}
            >
              {busy ? "Assessing…" : "Run assessment"}
            </button>
          </div>
        </div>
      ) : null}

      {recalculate.isError ? (
        <p role="alert" style={{ color: "var(--cw-status-not-satisfied)" }}>
          {/* Deliberately not "nothing has changed": a timeout or a dropped response
              after commit would make that false, and the user would be told the case is
              unchanged while looking at a list that is out of date. */}
          We couldn’t confirm whether that recalculation ran. Reload the page to see the
          current state.
        </p>
      ) : null}

      {status === "success" && withResults.length > 0 ? (
        <div className="cw-requirement-groups">
          {groups.map((group) => (
            <section
              key={group.key}
              className="cw-requirement-group"
              aria-labelledby={`group-${group.key}`}
            >
              <h3 id={`group-${group.key}`}>{GROUP_LABELS[group.key] ?? group.key}</h3>
              <GroupHeadingSummary
                summary={groupSummaries.find((s) => s.group_key === group.key)}
                fallbackCount={group.items.length}
              />
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

/**
 * A group's state in one line: how many requirements it holds, how many have not been
 * assessed, and whether any member is stale.
 *
 * The stale marker is the point (ADR-0010). Each row below carries its own currency, but
 * a reader scanning group headings would otherwise see "Residence — 5 requirements" and
 * take the group as current while one member's arithmetic is out of date.
 */
function GroupHeadingSummary({
  summary,
  fallbackCount,
}: {
  summary: GroupSummary | undefined;
  fallbackCount: number;
}) {
  const total = summary?.total ?? fallbackCount;
  return (
    <p className="cw-requirement-group__summary">
      <span>{total === 1 ? "1 requirement" : `${total} requirements`}</span>
      {summary && summary.not_yet_assessed > 0 ? (
        <span>· {summary.not_yet_assessed} not yet assessed</span>
      ) : null}
      {summary && summary.stale > 0 ? (
        <span className="cw-group-stale">
          <span aria-hidden="true">·</span>
          <StatusGlyph name="clock" size={14} />
          <span>
            {summary.stale === 1 ? "1 conclusion is stale" : `${summary.stale} conclusions are stale`}
          </span>
        </span>
      ) : null}
    </p>
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
