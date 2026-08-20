"use client";

import type { JSX } from "react";

import { IssueCard } from "@cw/design-system";

import { useRecalculate } from "@/features/case-workspace/useRecalculate";
import { formatDateTime } from "@/features/requirements/dates";
import { REQUIREMENT_TITLES } from "@/features/requirements/groups";

import { groupHeading, type Issue } from "./groups";
import { useIssueQueue } from "./useIssueQueue";

/**
 * The Issues destination: everything the case needs from the user, in one place.
 *
 * Two decisions worth stating, because both are visible and neither is obvious.
 *
 * **This is not a second copy of the requirements list.** A reached negative conclusion —
 * "presence on the first day is not currently satisfied" — is a requirement outcome and
 * appears as a priority action on Overview, not here. Issues are data problems and
 * process state: something is stale, uncertain, conflicting or unchecked. Without that
 * line the queue and the requirements list say the same thing twice in different words
 * (ADR-0014).
 *
 * **An empty queue is a real statement.** "Nothing needs your attention" means the system
 * looked and found nothing, which is only sayable because derivation runs over every
 * displayed result. A failed fetch must therefore never render as empty — it renders as
 * an error, because silence and "all clear" must not look alike.
 */
export function IssuesDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data: queue, status, refetch, isFetching } = useIssueQueue(caseId);

  if (status === "pending") {
    return <div className="cw-overview__placeholder" aria-hidden="true" />;
  }

  if (status === "error" || !queue) {
    return (
      <section aria-labelledby="issues-heading">
        <h2 id="issues-heading" className="cw-case-data__heading">
        Issues
      </h2>
        <p role="alert" className="cw-overview__unavailable">
          This queue couldn’t be loaded, so we can’t tell you whether anything needs your
          attention. This is not the same as nothing being wrong.
        </p>
        <button
          type="button"
          className="cw-button cw-button--secondary"
          onClick={() => void refetch()}
          aria-disabled={isFetching}
        >
          {isFetching ? "Retrying…" : "Try again"}
        </button>
      </section>
    );
  }

  return (
    <section aria-labelledby="issues-heading">
      <h2 id="issues-heading" className="cw-case-data__heading">
        Issues
      </h2>
      <p className="cw-case-data__note">
        Data problems and conclusions awaiting a recheck. Requirement outcomes live under
        Requirements.
      </p>

      {queue.open_count === 0 ? (
        <p className="cw-issue-queue__settled">
          Nothing needs your attention. Every conclusion reached so far is current, and no
          problems were found in your case data.
        </p>
      ) : (
        queue.groups.map((group) => (
          <IssueGroupSection key={group.action_group} caseId={caseId} group={group} />
        ))
      )}

      {queue.history.length > 0 ? <ResolvedHistory issues={queue.history} /> : null}
    </section>
  );
}

function IssueGroupSection({
  caseId,
  group,
}: {
  caseId: string;
  group: { action_group: string; issues: Issue[] };
}): JSX.Element {
  const headingId = `issue-group-${group.action_group}`;
  return (
    <section className="cw-issue-group" aria-labelledby={headingId}>
      <div className="cw-issue-group__head">
        <h3 id={headingId} className="cw-issue-group__heading">
          {groupHeading(group.action_group)}
        </h3>
        {/* A count, never a fraction: "3 of 9" would be a completion measure by another
            name (CLAUDE.md §2.6). */}
        <span className="cw-issue-group__count">
          {group.issues.length === 1 ? "1 item" : `${group.issues.length} items`}
        </span>
      </div>

      <ul className="cw-issue-group__list">
        {group.issues.map((issue) => (
          <li key={issue.id}>
            <IssueCard
              title={issue.title}
              severity={issue.severity as "BLOCKING" | "ACTION_REQUIRED" | "REVIEW_REQUIRED" | "INFORMATION"}
              body={issue.body}
              impact={issue.impact}
              hasRecurred={issue.has_recurred}
              affectedLink={<AffectedLink caseId={caseId} issue={issue} />}
              actions={
                issue.issue_type === "STALE_ASSESSMENT" ? <RecalculateAction caseId={caseId} /> : null
              }
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function AffectedLink({ caseId, issue }: { caseId: string; issue: Issue }): JSX.Element | null {
  if (issue.affected_object_type !== "Requirement") return null;
  const key = issue.affected_object_id;
  const label = REQUIREMENT_TITLES[key] ?? key;
  return (
    <a
      className="cw-issue-card__link"
      href={`/cases/${caseId}/requirements/${encodeURIComponent(key)}`}
    >
      Open {label}
    </a>
  );
}

/**
 * The one action a stale issue offers. It shares `useRecalculate` with the header rather
 * than owning a second mutation: two `useMutation` instances do not share state, so a
 * failure triggered here would have shown a sighted user nothing — the defect that reached
 * a running product at M4.
 */
function RecalculateAction({ caseId }: { caseId: string }): JSX.Element {
  const { mutation, announcement } = useRecalculate(caseId);
  const busy = mutation.isPending;
  return (
    <>
      <button
        type="button"
        className="cw-button cw-button--secondary"
        onClick={() => (busy ? undefined : mutation.mutate())}
        aria-disabled={busy}
      >
        {busy ? "Rechecking…" : "Recheck now"}
      </button>
      <p aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </p>
      {mutation.isError ? (
        <p role="alert" className="cw-case-header__error">
          We couldn’t confirm whether that recheck ran. Reload the page to see the current
          state.
        </p>
      ) : null}
    </>
  );
}

/**
 * Issues that are no longer open. Retained rather than deleted (Domain §36.6): "this was
 * raised and cleared" is part of what the case says about itself, and a queue that empties
 * without trace makes a resolved problem indistinguishable from one that never happened.
 */
function ResolvedHistory({ issues }: { issues: Issue[] }): JSX.Element {
  return (
    <section aria-labelledby="issue-history-heading">
      <h3 id="issue-history-heading" className="cw-issue-group__heading cw-issue-history__heading">
        Settled
      </h3>
      <ul className="cw-issue-history">
        {issues.map((issue) => (
          <li key={issue.id} className="cw-issue-history__item">
            <span className="cw-issue-history__title">{issue.title}</span>
            <span>
              {issue.status === "DISMISSED" ? "Dismissed" : "Resolved"}
              {issue.resolved_at ? ` · ${formatDateTime(issue.resolved_at)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
