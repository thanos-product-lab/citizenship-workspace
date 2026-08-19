"use client";

import type { components } from "@cw/api-client";
import { StatusGlyph } from "@cw/design-system";
import type { JSX } from "react";

import { GROUP_LABELS } from "@/features/requirements/groups";

import { groupLine } from "./narrative";

type Overview = components["schemas"]["CaseOverview"];
type Group = components["schemas"]["GroupSummaryView"];

/** A group's display name, humanised rather than shown raw if the label map lags the
 *  catalogue — a bare `REFEREES` should never land inside a sentence. */
function groupLabel(key: string): string {
  const known = GROUP_LABELS[key];
  if (known) return known;
  const words = key.toLowerCase().replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/**
 * Where the case stands by group, and the way through to Requirements.
 *
 * **Every row is counts of named states — never a fraction.** `4 / 4 supported` and
 * `0 / 2 assessed` are readiness scores arrived at sideways: a reader converts `4 / 5` to
 * 80%. Worse, `Residence 4 / 5` renders a `NOT_CURRENTLY_SATISFIED` conclusion as
 * *missing* — as though finding a fifth thing would complete the set — silently converting
 * a reached failure into an incomplete. The sanctioned form is counts with no denominator:
 * UI/UX §6.2, CLAUDE.md §2.6.
 *
 * Nor is a group given a single verdict of its own. "Residence: not currently satisfied"
 * would be a claim about five requirements on the strength of one, and there is no rule
 * that concludes anything about a group. The row states what its members said and stops.
 *
 * The per-group stale count says *where* staleness is, which the case-level signal in the
 * header cannot: the header says how many conclusions are unrechecked, this says which
 * part of the case they are in.
 */
export function AssessmentGroups({ overview }: { overview: Overview }): JSX.Element | null {
  if (overview.groups.length === 0) return null;

  return (
    <section className="cw-assessment-groups" aria-labelledby="assessment-heading">
      <h3 id="assessment-heading">Assessment</h3>

      <ul className="cw-group-rows">
        {overview.groups.map((group) => (
          <GroupRow key={group.group_key} group={group} caseId={overview.case_id} />
        ))}
      </ul>

      <a className="cw-assessment-groups__all" href={`/cases/${overview.case_id}/requirements`}>
        View all requirements <span aria-hidden="true">→</span>
      </a>
    </section>
  );
}

function GroupRow({ group, caseId }: { group: Group; caseId: string }): JSX.Element {
  const line = groupLine(group);
  const stateId = `group-state-${group.group_key}`;

  return (
    <li className="cw-group-row">
      {/*
        The link is described by its state rather than containing it. A screen-reader user
        listing links hears "Residence", not a forty-character sentence, but focusing the
        link still announces how the group stands — which a visually adjacent span alone
        would not convey.

        The fragment deep-links to the group's heading on the Requirements destination;
        `RequirementsList` scrolls to it once its data has arrived, since the target does
        not exist at navigation time.
      */}
      <a
        className="cw-group-row__link"
        href={`/cases/${caseId}/requirements#group-${group.group_key}`}
        aria-describedby={line ? stateId : undefined}
      >
        {groupLabel(group.group_key)}
      </a>

      <span className="cw-group-row__state" id={stateId}>
        {line}
      </span>

      {group.stale > 0 ? (
        <span className="cw-group-row__stale">
          <StatusGlyph name="clock" size={14} />
          <span>
            {group.stale === 1 ? "1 stale" : `${group.stale} stale`}
          </span>
        </span>
      ) : null}
    </li>
  );
}
