"use client";

import type { components } from "@cw/api-client";
import { StatusGlyph } from "@cw/design-system";
import type { JSX } from "react";

import { formatDate } from "@/features/requirements/dates";

import { GROUP_LABELS } from "@/features/requirements/groups";

import { busiestGroup, conclusionLines, phaseHeading, unassessedLine } from "./narrative";

/** A group's display name. An unlabelled key is humanised rather than shown raw, so a
 *  catalogue addition never drops `REFEREES` into the middle of a sentence. */
function groupLabel(key: string): string {
  const known = GROUP_LABELS[key];
  if (known) return known;
  const words = key.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

type Overview = components["schemas"]["CaseOverview"];

/**
 * The head of the case: where you stand, and the few things worth doing next.
 *
 * What this screen must not do, and how it avoids each:
 *
 * - **Show a readiness score.** No fraction, percentage, or progress measure appears.
 *   The counts are of named states, and the number of unassessed requirements is stated
 *   as its own fact rather than as a remainder.
 * - **Let staleness hide behind a summary.** A case with any stale result carries a
 *   banner here, and each group heading states how many of its conclusions are stale
 *   (ADR-0010). The group's own `currency` is not rendered yet — when M6 introduces
 *   PROVISIONAL results a count of stale conclusions will no longer be sufficient.
 * - **Imply an outcome.** The heading comes from the derived case phase (ADR-0009); the
 *   one narrative line names where the outstanding work is, from a count comparison.
 *   Nothing predicts whether an application would succeed.
 */
export function CaseOverviewPanel({
  overview,
  updating = false,
}: {
  overview: Overview;
  /** A refetch is in flight, so the figures below describe the state before the write
      that triggered it. Saying so is the difference between a slow update and a summary
      quietly presenting superseded counts as current. */
  updating?: boolean;
}): JSX.Element {
  const lines = conclusionLines(overview);
  const unassessed = unassessedLine(overview);
  const busiest = busiestGroup(overview);

  return (
    <section className="cw-overview" aria-label="Case overview">
      <dl className="cw-overview__facts">
        {overview.application_date ? (
          <div>
            <dt>Proposed application date</dt>
            <dd className="cw-figure">{formatDate(overview.application_date)}</dd>
          </div>
        ) : null}
        <div>
          <dt>Route</dt>
          <dd>Standard five-year route</dd>
        </div>
        {overview.last_assessed_at ? (
          <div>
            <dt>Last assessed</dt>
            <dd className="cw-figure">{formatDate(overview.last_assessed_at)}</dd>
          </div>
        ) : null}
      </dl>

      <h2 className="cw-overview__heading">{phaseHeading(overview.current_phase)}</h2>

      {updating ? (
        <p className="cw-updating" aria-live="polite">
          <StatusGlyph name="clock" size={14} />
          <span>Updating — these figures are from before your last change.</span>
        </p>
      ) : null}

      {lines.length === 0 && !unassessed ? (
        <p className="cw-overview__empty">
          No requirements are catalogued for this route yet.
        </p>
      ) : (
        <ul className="cw-overview__counts" aria-label="Requirements by state">
          {lines.map((line) => (
            <li key={line.key}>
              <span className="cw-overview__count cw-figure">{line.count}</span>{" "}
              <span>{line.label.toLowerCase()}</span>
            </li>
          ))}
          {/* The unassessed count is its own fact, never "the rest": a requirement
              nothing has decided is not progress waiting to be counted. */}
          {unassessed ? (
            <li key={unassessed.key} data-unassessed="true">
              <span className="cw-overview__count cw-figure">{unassessed.count}</span>{" "}
              <span>not yet assessed</span>
            </li>
          ) : null}
        </ul>
      )}

      {busiest ? (
        <p className="cw-overview__where">
          Of the requirements that need attention, most are in{" "}
          <strong>{groupLabel(busiest.group_key)}</strong>.
          {overview.not_yet_assessed > 0
            ? " Requirements that haven’t been assessed yet aren’t counted here."
            : ""}
        </p>
      ) : null}

      {overview.stale > 0 ? (
        <p className="cw-overview__stale">
          <StatusGlyph name="clock" size={16} />
          <span>
            {overview.stale === 1
              ? "1 conclusion has not been rechecked"
              : `${overview.stale} conclusions have not been rechecked`}{" "}
            since your inputs changed. They are shown as they were reached, marked stale.
          </span>
        </p>
      ) : null}

      <PriorityActions overview={overview} />
    </section>
  );
}

/**
 * At most three actions (UI/UX §6.4). The cap is about attention, so when more exist the
 * panel says how many it is not showing — a cap that silently hides work misleads.
 * Every action links to the requirement that raised it, so the full reasoning is one
 * click away rather than compressed into the line.
 */
function PriorityActions({ overview }: { overview: Overview }): JSX.Element | null {
  if (overview.priority_actions.length === 0) return null;
  return (
    <section className="cw-actions" aria-labelledby="actions-heading">
      <h3 id="actions-heading">What to do next</h3>
      <ol className="cw-actions__list">
        {overview.priority_actions.map((action) => (
          <li
            key={`${action.requirement_key}-${action.code}-${JSON.stringify(action.parameters)}`}
            className="cw-action-card"
          >
            <a
              className="cw-action-card__title"
              href={`/cases/${overview.case_id}/requirements/${encodeURIComponent(action.requirement_key)}`}
            >
              {action.requirement_title}
            </a>
            <p className="cw-action-card__text">{action.text ?? action.code}</p>
            {action.currency === "STALE" ? (
              // The ask is usually still right, but it was computed from arithmetic the
              // system has already flagged as not rechecked. Saying so here is the only
              // correction available: unlike a group tile, an action card has no second
              // badge, and "cannot be satisfied until this is resolved" below would
              // otherwise read as a settled fact.
              <p className="cw-action-card__flag" data-stale="true">
                <StatusGlyph name="clock" size={14} />
                <span>
                  Based on figures that haven’t been rechecked since your inputs changed.
                </span>
              </p>
            ) : null}
            {action.blocking ? (
              <p className="cw-action-card__flag">
                <StatusGlyph name="minus-circle" size={14} />
                <span>This requirement cannot be satisfied until this is resolved.</span>
              </p>
            ) : null}
          </li>
        ))}
      </ol>
      {overview.priority_actions_hidden > 0 ? (
        <p className="cw-actions__more">
          {overview.priority_actions_hidden === 1
            ? "1 more action isn’t shown here. Open its requirement below to see it."
            : `${overview.priority_actions_hidden} more actions aren’t shown here. Open the requirements below to see them.`}
        </p>
      ) : null}
    </section>
  );
}
