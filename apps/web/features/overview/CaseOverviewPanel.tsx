"use client";

import type { components } from "@cw/api-client";
import { RequirementStatus } from "@cw/design-system";
import type { JSX } from "react";

import { GROUP_LABELS } from "@/features/requirements/groups";

import { busiestGroup, conclusionLines, readinessHeadline, unassessedLine } from "./narrative";

type Overview = components["schemas"]["CaseOverview"];

/** A group's display name, humanised rather than shown raw if the label map lags the
 *  catalogue — a bare `REFEREES` should never land inside a sentence. */
function groupLabel(key: string): string {
  const known = GROUP_LABELS[key];
  if (known) return known;
  const words = key.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * The readiness summary: where you stand, and the few things worth doing next.
 *
 * This is the Overview destination's whole content. Case identity, metadata, currency and
 * the recalculate command live in the persistent case header, because they belong to the
 * case rather than to this page; the requirements themselves live under Requirements.
 * What remains here is two levels:
 *
 * - **Readiness** leads with the count of requirements that need the user and keeps the
 *   named-state counts beneath it, quieter. The counts are not dropped: CLAUDE.md §2.6
 *   requires the qualitative states, and they are the only place `NEAR_THRESHOLD` and the
 *   unassessed count are visible.
 * - **Immediate action** is one card per action, each carrying the requirement's own
 *   conclusion badge and the server's action text. No sentence here is composed in this
 *   file — assessment copy comes from the deterministic templates.
 *
 * What this screen must not do:
 *
 * - **Show a readiness score.** No fraction, percentage, ratio or progress measure. The
 *   unassessed count is stated as its own fact, never as a remainder — `6 not yet
 *   assessed` is a fact, `9 / 15` is a completion measure a reader converts to 60%.
 * - **Imply an outcome.** Nothing predicts whether an application would succeed.
 */
export function CaseOverviewPanel({ overview }: { overview: Overview }): JSX.Element {
  const lines = conclusionLines(overview);
  const unassessed = unassessedLine(overview);
  const busiest = busiestGroup(overview);
  const hasCounts = lines.length > 0 || unassessed !== null;

  return (
    <section className="cw-overview" aria-label="Case overview">
      <h2 className="cw-overview__heading">{readinessHeadline(overview)}</h2>

      {hasCounts ? (
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
      ) : (
        <p className="cw-overview__empty">No requirements are catalogued for this route yet.</p>
      )}

      <PriorityActions overview={overview} busiestGroupKey={busiest?.group_key ?? null} />
    </section>
  );
}

/**
 * At most three actions (UI/UX §6.4).
 *
 * Each card carries the requirement's **conclusion** badge, not a "Blocking" chip.
 * Blocking is a property of the action, not a conclusion, and putting it where a status
 * badge sits would read as a ninth conclusion state — collapsing the two axes ADR-0001
 * keeps apart. It is stated once, quietly, as the card's own meta.
 *
 * The action sentence is the server's rendered text. Nothing here composes prose about an
 * assessment.
 */
function PriorityActions({
  overview,
  busiestGroupKey,
}: {
  overview: Overview;
  busiestGroupKey: string | null;
}): JSX.Element | null {
  if (overview.priority_actions.length === 0) return null;

  return (
    <section className="cw-actions" aria-labelledby="actions-heading">
      <h3 id="actions-heading">Needs your attention</h3>

      <ol className="cw-actions__list">
        {overview.priority_actions.map((action) => (
          <li
            key={`${action.requirement_key}-${action.code}-${JSON.stringify(action.parameters)}`}
            className="cw-action-card"
            data-blocking={action.blocking ? "true" : undefined}
          >
            <div className="cw-action-card__head">
              <span className="cw-action-card__title">{action.requirement_title}</span>
              <RequirementStatus
                conclusion={action.conclusion}
                currency={action.currency}
                size="sm"
              />
            </div>

            <p className="cw-action-card__text">{action.text ?? action.code}</p>

            <p className="cw-action-card__meta">
              {action.blocking ? <span>Blocks this requirement</span> : null}
              <a
                className="cw-action-card__link"
                href={`/cases/${overview.case_id}/requirements/${encodeURIComponent(action.requirement_key)}`}
              >
                Review requirement <span aria-hidden="true">→</span>
              </a>
            </p>
          </li>
        ))}
      </ol>

      {/* Where the rest of the work sits, and what the count above does not cover. Both
          are scoped statements: the comparison is over assessed requirements only. */}
      {busiestGroupKey || overview.priority_actions_hidden > 0 ? (
        <p className="cw-actions__more">
          {overview.priority_actions_hidden > 0
            ? `${overview.priority_actions_hidden === 1 ? "1 more action isn’t" : `${overview.priority_actions_hidden} more actions aren’t`} shown here — open the requirement to see it. `
            : ""}
          {busiestGroupKey
            ? `Most of what needs attention is in ${groupLabel(busiestGroupKey)}.`
            : ""}
          {overview.not_yet_assessed > 0
            ? " Requirements that haven’t been assessed yet aren’t counted."
            : ""}
        </p>
      ) : null}
    </section>
  );
}
