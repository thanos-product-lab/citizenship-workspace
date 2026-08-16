"use client";

import type { components } from "@cw/api-client";
import { StatusGlyph } from "@cw/design-system";
import type { JSX } from "react";

import { formatDate } from "@/features/requirements/dates";

import { busiestGroup, conclusionLines, phaseHeading, unassessedLine } from "./narrative";
import { GROUP_LABELS } from "@/features/requirements/groups";

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
 *   banner here, and each group heading carries its own currency (ADR-0010).
 * - **Imply an outcome.** The heading comes from the derived case phase (ADR-0009); the
 *   one narrative line names where the outstanding work is, from a count comparison.
 *   Nothing predicts whether an application would succeed.
 */
export function CaseOverviewPanel({ overview }: { overview: Overview }): JSX.Element {
  const lines = conclusionLines(overview);
  const unassessed = unassessedLine(overview);
  const busiest = busiestGroup(overview);

  return (
    <section className="cw-overview" aria-labelledby="overview-heading">
      <div className="cw-overview__facts">
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
      </div>

      <h2 id="overview-heading" className="cw-overview__heading">
        {phaseHeading(overview.current_phase)}
      </h2>

      {lines.length === 0 && !unassessed ? (
        <p className="cw-overview__empty">
          No requirements are catalogued for this route yet.
        </p>
      ) : (
        <ul className="cw-overview__counts">
          {lines.map((line) => (
            <li key={line.key}>
              <span className="cw-overview__count cw-figure">{line.count}</span>
              <span>{line.label.toLowerCase()}</span>
            </li>
          ))}
          {unassessed ? (
            <li key={unassessed.key} data-unassessed="true">
              <span className="cw-overview__count cw-figure">{unassessed.count}</span>
              {/* Stated as its own fact, never as "the rest": a requirement nothing has
                  decided is not progress waiting to be counted. */}
              <span>not yet assessed</span>
            </li>
          ) : null}
        </ul>
      )}

      {busiest ? (
        <p className="cw-overview__where">
          Most of the outstanding work is in{" "}
          <strong>{GROUP_LABELS[busiest.group_key] ?? busiest.group_key}</strong>.
        </p>
      ) : null}

      {overview.stale > 0 ? (
        <p className="cw-overview__stale" role="status">
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
          <li key={`${action.requirement_key}-${action.code}`} className="cw-action-card">
            <a
              className="cw-action-card__title"
              href={`/cases/${overview.case_id}/requirements/${encodeURIComponent(action.requirement_key)}`}
            >
              {action.requirement_title}
            </a>
            <p className="cw-action-card__text">{action.text ?? action.code}</p>
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
            ? "1 more action is listed against its requirement below."
            : `${overview.priority_actions_hidden} more actions are listed against their requirements below.`}
        </p>
      ) : null}
    </section>
  );
}
