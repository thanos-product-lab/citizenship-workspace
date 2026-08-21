"use client";

import type { components } from "@cw/api-client";
import { StatusGlyph } from "@cw/design-system";
import type { JSX, RefObject } from "react";

import { formatDate } from "@/features/requirements/dates";

import { CaseNavigation } from "./CaseNavigation";
import { useCaseOverview } from "./useCaseOverview";
import { useRecalculate, useRecalculationInFlight } from "./useRecalculate";

type Case = components["schemas"]["CaseResponse"];

const PHASE_LABEL: Record<string, string> = {
  SETTING_UP: "Setting up",
  BUILDING_CASE: "Building your case",
  RESOLVING_ISSUES: "Resolving issues",
  NEARLY_PREPARED: "Nearly prepared",
  FINAL_REVIEW: "Final review",
};

/**
 * The case identity, carried across every destination.
 *
 * Three things live here rather than on a page, and each for the same reason — they are
 * properties of the *case*, not of whichever destination you happen to be reading:
 *
 * 1. **Identity and metadata.** Title, derived phase (ADR-0009), proposed application
 *    date and route. Enough to orient, deliberately not the readiness summary — that
 *    belongs to Overview and repeating it on every page would make the header the screen.
 *
 * 2. **Currency.** This is the important one. Staleness is *caused* by editing an input,
 *    which after the workspace split happens under Case data. If the stale notice lived
 *    only on Overview, a user could change a trip on one destination while the notice
 *    that their conclusions are now stale appeared on another they need not revisit —
 *    separating staleness from its own cause. A destination that shows editable inputs
 *    while omitting that the conclusions drawn from them are stale is presenting
 *    superseded state as current, which is what directives §2.4 and §2.7 exist to stop.
 *
 * 3. **Recalculate.** A case-level command: it creates a new `AssessmentRun` and new
 *    results for every requirement, not only the ones on screen. Left inside the
 *    requirements list it would read as recalculating that destination alone.
 */
export function CaseHeader({
  caseData,
  headingRef,
}: {
  caseData: Case;
  headingRef: RefObject<HTMLHeadingElement | null>;
}): JSX.Element {
  const { data: overview } = useCaseOverview(caseData.id);

  return (
    <header className="cw-case-header">
      <a className="cw-case-header__back" href="/">
        <span aria-hidden="true">←</span> Your cases
      </a>

      <div className="cw-case-header__identity">
        <h1 className="cw-case-header__title" ref={headingRef} tabIndex={-1}>
          {caseData.title}
        </h1>
        <span className="cw-phase-chip">
          <span className="cw-visually-hidden">Case phase: </span>
          {PHASE_LABEL[caseData.current_phase] ?? caseData.current_phase}
        </span>
        <RecalculateButton caseId={caseData.id} />
      </div>

      {/* Label/value pairs as a description list, so the labels are programmatically
          associated with their values rather than merely adjacent to them. */}
      <dl className="cw-case-header__facts">
        {overview?.application_date ? (
          <div>
            <dt>Proposed application date</dt>
            <dd className="cw-figure">{formatDate(overview.application_date)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Route</dt>
          <dd>Standard five-year route</dd>
        </div>
        {overview?.last_assessed_at ? (
          <div>
            <dt>Last assessed</dt>
            <dd className="cw-figure">{formatDate(overview.last_assessed_at)}</dd>
          </div>
        ) : null}
      </dl>

      <CaseNavigation caseId={caseData.id} />

      {/* Currency sits below the navigation, so it reads as qualifying every destination
          rather than belonging to the header's own metadata. */}
      <CaseCurrency caseId={caseData.id} />
    </header>
  );
}

/**
 * The case-level currency signals: a recalculation in flight, and unrechecked conclusions.
 *
 * Both are stated once, here, rather than repeated per destination. The stale sentence
 * never claims the conclusion still holds — that is precisely what a stale result cannot
 * tell us — it says the conclusion is shown as it was reached.
 */
function CaseCurrency({ caseId }: { caseId: string }): JSX.Element | null {
  const { data: overview, isFetching, status } = useCaseOverview(caseId);

  if (status !== "success" || !overview) return null;

  return (
    <>
      {isFetching ? (
        <p className="cw-updating" aria-live="polite">
          <StatusGlyph name="clock" size={14} />
          <span>Updating — the figures and conclusions shown are from before your last change.</span>
        </p>
      ) : null}

      {overview.stale > 0 ? (
        <p className="cw-case-header__stale">
          <StatusGlyph name="clock" size={16} />
          <span>
            {overview.stale === 1
              ? "1 conclusion has not been rechecked"
              : `${overview.stale} conclusions have not been rechecked`}{" "}
            since your inputs changed. They are shown as they were reached, marked stale.
          </span>
        </p>
      ) : null}
    </>
  );
}

/**
 * Recalculate the whole case. Hidden until the case has been assessed once — before that
 * the affordance is "Run assessment" in the requirements list's empty state, so that the
 * first run is offered where its absence is being explained.
 */
function RecalculateButton({ caseId }: { caseId: string }): JSX.Element | null {
  const { data: overview, isFetching, status } = useCaseOverview(caseId);
  const { mutation: recalculate, announcement } = useRecalculate(caseId);

  // Shared across every recalculation control on the page, not just this one's observer.
  // The group's Recheck on the Issues destination runs the same case-wide command, and
  // two controls each tracking only their own `isPending` leave the other looking idle
  // while a run is in flight.
  const inFlight = useRecalculationInFlight(caseId);
  const busy = inFlight || recalculate.isPending || (isFetching && status === "success");

  // Nothing to recalculate until the case has been assessed once. `conclusion_counts`
  // excludes NOT_YET_ASSESSED, so this is "at least one requirement has a conclusion" —
  // the same question the requirements list used to ask of its own rows.
  const assessed = (overview?.conclusion_counts ?? []).reduce((total, c) => total + c.count, 0);

  if (status !== "success" || assessed === 0) return null;

  return (
    <>
      <button
        type="button"
        className="cw-button cw-button--secondary cw-case-header__recalculate"
        onClick={() => (busy ? undefined : recalculate.mutate())}
        // aria-disabled, not disabled: a focused button that becomes `disabled` is blurred
        // by the browser, silently dropping focus mid-operation.
        aria-disabled={busy}
      >
        {busy ? "Recalculating…" : "Recalculate"}
      </button>
      {/* Mounted unconditionally: a live region whose container and text arrive in the
          same commit is frequently missed by NVDA and JAWS. */}
      <p aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </p>

      {/* A visible failure, not only an announced one. The control that failed lives here,
          so the report has to live here too — a sighted user would otherwise see the
          button settle and nothing change.

          Says nothing about whether the figures moved. A server-side failure leaves them
          alone, but a timeout or a dropped response *after* the run committed lands here
          too and there they changed — one sentence has to be true of both. It no longer
          tells the user to reload either: the hook refetches on error, so the screen is
          already showing whatever the server has. */}
      {recalculate.isError ? (
        <p role="alert" className="cw-case-header__error">
          That recalculation didn’t finish. The screen has been refreshed with what the
          server recorded.
        </p>
      ) : null}
    </>
  );
}
