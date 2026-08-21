"use client";

import { type JSX, useEffect, useRef, useState } from "react";

import { IssueCard } from "@cw/design-system";

import { useCaseOverview } from "@/features/case-workspace/useCaseOverview";
import {
  useRecalculate,
  useRecalculationInFlight,
} from "@/features/case-workspace/useRecalculate";
import { formatDateTime } from "@/features/requirements/dates";
import { REQUIREMENT_TITLES } from "@/features/requirements/groups";

import { groupHeading, type Issue, type IssueGroup } from "./groups";
import { useDismissIssue } from "./useDismissIssue";
import { useIssueQueue } from "./useIssueQueue";

/**
 * The Issues destination: everything the case needs from the user, in one place.
 *
 * Three decisions worth stating, because each is visible and none is obvious.
 *
 * **This is not a second copy of the requirements list.** A reached negative conclusion —
 * "presence on the first day is not currently satisfied" — is a requirement outcome and
 * appears as a priority action on Overview, not here. Issues are data problems and process
 * state. Without that line the queue and the requirements list say the same thing twice in
 * different words (ADR-0014).
 *
 * **An empty queue is a real statement.** "Nothing needs your attention" means the system
 * looked and found nothing. A failed fetch must therefore never render as empty — silence
 * and all-clear must not look alike.
 *
 * **One recheck control, not one per card.** Every stale issue is cleared by the same
 * case-wide recalculation, so a button on each card would be N identically-named controls
 * that all do one thing — and activating a second while the first was in flight fired a
 * concurrent recalculation. The group owns the action.
 */
export function IssuesDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data: queue, status, refetch, isFetching } = useIssueQueue(caseId);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [announcement, setAnnouncement] = useState("");
  // State, not a ref: setting a ref does not re-render, so an effect keyed on it would
  // never run and focus would silently stay on the control that just unmounted.
  const [returnFocus, setReturnFocus] = useState(false);

  // A control that unmounts takes keyboard focus with it, dropping the user to <body>.
  // Both the recheck button and the retry button disappear on success, so focus is parked
  // on the heading once the refetch settles.
  useEffect(() => {
    if (returnFocus && status !== "pending" && !isFetching) {
      setReturnFocus(false);
      headingRef.current?.focus();
    }
  }, [returnFocus, status, isFetching]);

  const openCount = queue?.open_count ?? 0;

  // Announce from *observed* state, not from a mutation callback.
  //
  // The obvious implementation passes onSuccess to mutate() from the button. React Query
  // drops those callbacks when the calling component unmounts — and clearing the queue
  // unmounts the group the button lives in, so the announcement never fires and focus is
  // never returned. A jsdom test does not catch it, because the mocked mutation settles
  // before the unmount; the browser does. So the parent records only that a recheck was
  // asked for, and derives what to say from the count actually changing.
  // The dismiss mutation lives here, not in the card. React Query drops callbacks passed
  // to mutate() when the calling component unmounts, and a dismissed card is removed by
  // the refetch its own success triggers — the same trap that swallowed the recheck
  // announcement. A parent that outlives the list is the only safe owner.
  const dismiss = useDismissIssue(caseId);
  const [recheckRequested, setRecheckRequested] = useState(false);
  const recheckBaseline = useRef(openCount);
  const recheckInFlight = useRecalculationInFlight(caseId);

  // Fire when the recheck *settles*, not when the count moves.
  //
  // Gating on the count was wrong in a way no test covered: a recalculation that resolves
  // one stale issue and opens one fresh one is net zero, so nothing was announced, the
  // flag was never cleared, and — because the group unmounts with its last stale item —
  // focus was never returned and the user landed on <body>. That is the same 2.4.3 / 4.1.3
  // failure two earlier commits were written to fix, still reachable through the one path
  // the count heuristic could not see. Worse, the flag stayed armed, so the *next* thing
  // to move the count (a dismissal) was announced as "recheck finished, 1 issue resolved"
  // — reporting a recheck that never happened and calling a dismissal a resolution.
  //
  // The count now only chooses the wording.
  useEffect(() => {
    if (!recheckRequested || recheckInFlight || isFetching || status === "pending") return;

    const previous = recheckBaseline.current;
    const cleared = previous - openCount;
    setAnnouncement(
      cleared > 0
        ? `Recheck finished. ${cleared === 1 ? "1 issue" : `${cleared} issues`} resolved.` +
            (openCount === 0 ? " Nothing needs your attention." : "")
        : "Recheck finished. Nothing was resolved.",
    );
    setRecheckRequested(false);
    setReturnFocus(true);
  }, [openCount, recheckRequested, recheckInFlight, isFetching, status]);

  return (
    <section aria-labelledby="issues-heading">
      <h2 id="issues-heading" className="cw-case-data__heading" ref={headingRef} tabIndex={-1}>
        Issues
      </h2>
      <p className="cw-case-data__note">
        Data problems and conclusions awaiting a recheck. Requirement outcomes live under
        Requirements.
      </p>

      {/* One live region for the destination, mounted unconditionally. It lives here
          rather than inside a card because the card is destroyed by the very action it
          announces — a state update on an unmounted component says nothing at all. */}
      <p aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </p>

      {status === "error" || (status !== "pending" && !queue) ? (
        <>
          <div role="alert" className="cw-overview__unavailable">
            <p>
              This queue couldn’t be loaded, so we can’t tell you whether anything needs
              your attention. This is not the same as nothing being wrong.
            </p>
          </div>
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => {
              setReturnFocus(true);
              setAnnouncement("Retrying.");
              void refetch();
            }}
            aria-disabled={isFetching}
          >
            {isFetching ? "Retrying…" : "Try again"}
          </button>
        </>
      ) : null}

      {status === "success" && queue ? (
        <>
          {openCount === 0 ? (
            <SettledStatement caseId={caseId} />
          ) : (
            <NotRecheckedNote queue={queue} />
          )}

          {queue.groups.map((group) => (
            <IssueGroupSection
              key={group.action_group}
              caseId={caseId}
              group={group}
              onRecheckRequested={() => {
                // Snapshot the count the outcome will be measured against, and say
                // something now: the label changing to "Rechecking…" and `aria-disabled`
                // going true are both silent to a screen reader, so without this the
                // user gets no feedback at all for the length of the request.
                recheckBaseline.current = openCount;
                setAnnouncement("Rechecking your conclusions.");
                setRecheckRequested(true);
              }}
              onRecheckFailed={() => {
                // Clear the flag but say nothing here. `RecheckAction` renders a
                // `role="alert"` for the same failure, which is assertive and lands first;
                // a polite message behind it repeats the same fact in slightly different
                // words and sounds like a second event. One failure, one announcer.
                //
                // Clearing matters on its own: a failure refetches the queue, which adds
                // the processing-failure item, so the count moves — and a still-armed
                // recheck would report "recheck finished" over a recheck that did not.
                setAnnouncement("");
                setRecheckRequested(false);
              }}
              dismissState={dismiss}
              onDismiss={(issue) => {
                dismiss.mutate(issue.id, {
                  onSuccess: () => {
                    setAnnouncement(
                      `${issue.title} dismissed. It is listed under Settled.`,
                    );
                    setReturnFocus(true);
                  },
                });
              }}
            />
          ))}

          {queue.history.length > 0 ? <ResolvedHistory issues={queue.history} /> : null}
        </>
      ) : null}
    </section>
  );
}

/**
 * The caveat that has to sit above the list when part of it is out of date.
 *
 * Items are derived from the *displayed* result, stale or current — suppressing them
 * during a stale window would make them vanish and reappear around every recalculation.
 * The cost is that a card can assert something in the present tense ("two of your trips
 * cover some of the same dates") from a computation the product knows is superseded.
 *
 * The stale items themselves say so, but they sit in their own action group and are never
 * adjacent to the ones they qualify. This states it once, above everything.
 */
function NotRecheckedNote({
  queue,
}: {
  queue: { groups: { issues: Issue[] }[] };
}): JSX.Element | null {
  const stale = queue.groups
    .flatMap((group) => group.issues)
    .filter((issue) => issue.issue_type === "STALE_ASSESSMENT").length;
  if (stale === 0) return null;
  return (
    <p className="cw-issue-queue__caveat">
      Some of these were worked out before your last change and have not been rechecked, so
      what they describe may have moved.
    </p>
  );
}

/**
 * The all-clear, which is only sayable when it is true of the whole case.
 *
 * The queue is a write-time projection: it is populated when an input changes, not
 * computed on read. A case whose results were staled before issue derivation existed —
 * or by any path that somehow bypassed the seam — would have stale conclusions and an
 * empty queue. So the sentence is gated on the case's own stale count as well, and
 * degrades to the narrower, still-true claim when the two disagree.
 */
function SettledStatement({ caseId }: { caseId: string }): JSX.Element {
  const { data: overview } = useCaseOverview(caseId);
  if (overview && overview.stale > 0) {
    return (
      <p className="cw-issue-queue__settled">
        No problems were found in your case data. Some conclusions have not been rechecked
        since your inputs changed — open Requirements to see which.
      </p>
    );
  }
  return (
    <p className="cw-issue-queue__settled">
      Nothing needs your attention. Every conclusion reached so far is current, and no
      problems were found in your case data.
    </p>
  );
}

function IssueGroupSection({
  caseId,
  group,
  onRecheckRequested,
  onRecheckFailed,
  onDismiss,
  dismissState,
}: {
  caseId: string;
  group: IssueGroup;
  onRecheckRequested: () => void;
  onRecheckFailed: () => void;
  onDismiss: (issue: Issue) => void;
  dismissState: { isPending: boolean; isError: boolean; variables?: string | undefined };
}): JSX.Element {
  const headingId = `issue-group-${group.action_group}`;
  // A processing failure is cleared by the same case-wide recalculation a stale conclusion
  // is, so it does not get a control of its own — it changes what this one is called. It
  // also earns the control on its own: a recalculation can fail on a case with nothing
  // stale, and without this that group would show the failure and no way to retry it.
  const failed = group.issues.some((issue) => issue.issue_type === "PROCESSING_FAILURE");
  const recheckable =
    failed || group.issues.some((issue) => issue.issue_type === "STALE_ASSESSMENT");

  return (
    <section className="cw-issue-group" aria-labelledby={headingId}>
      <div className="cw-issue-group__head">
        <h3 id={headingId} className="cw-issue-group__heading">
          {groupHeading(group.action_group)}
        </h3>
        {/* A count, never a fraction: "3 of 9" is a completion measure by another name. */}
        <span className="cw-issue-group__count">
          {group.issues.length === 1 ? "1 item" : `${group.issues.length} items`}
        </span>
      </div>

      {recheckable ? (
        <RecheckAction
          caseId={caseId}
          retry={failed}
          onRequested={onRecheckRequested}
          onFailed={onRecheckFailed}
        />
      ) : null}

      <ul className="cw-issue-group__list" role="list">
        {group.issues.map((issue) => (
          <li key={issue.id}>
            <IssueCard
              titleId={`issue-title-${issue.id}`}
              headingLevel={4}
              title={issue.title}
              severity={
                issue.severity as
                  | "BLOCKING"
                  | "ACTION_REQUIRED"
                  | "REVIEW_REQUIRED"
                  | "INFORMATION"
              }
              body={issue.body}
              impact={issue.impact}
              hasRecurred={issue.has_recurred}
              affectedLink={affectedLinkFor(caseId, issue)}
              actions={
                issue.dismissibility === "DISMISSIBLE" ? (
                  <DismissAction issue={issue} onDismiss={onDismiss} state={dismissState} />
                ) : null
              }
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * A way in to whatever the issue is about.
 *
 * Travel-record issues are precisely the ones a user must edit something to clear, so
 * without this they offer exactly one action — dismiss, where that is even allowed — and
 * "For your awareness" becomes a dead end with no keyboard path to the trip.
 *
 * A plain function rather than a component, because `IssueCard` decides whether to render
 * its footer from `affectedLink || actions` — and a JSX element is truthy even when it
 * renders `null`. As a component this left the processing-failure card, whose affected
 * object is the case itself, with an empty footer and its margin.
 */
function affectedLinkFor(caseId: string, issue: Issue): JSX.Element | null {
  if (issue.affected_object_type === "Requirement") {
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

  if (issue.affected_object_type === "TravelRecord") {
    // Case data owns the travel table. There is no per-trip route yet — the IA brief's
    // `/data/travel` is still deferred — so this lands on the page that owns the edit.
    return (
      <a className="cw-issue-card__link" href={`/cases/${caseId}/data`}>
        Open your travel history
      </a>
    );
  }

  return null;
}

/**
 * The group's recheck. Shares `useRecalculate` with the header rather than owning a second
 * mutation: separate `useMutation` instances do not share state, so a failure triggered
 * here would show a sighted user nothing there — the defect that reached a running product
 * at M4.
 */
function RecheckAction({
  caseId,
  retry,
  onRequested,
  onFailed,
}: {
  caseId: string;
  /** The last attempt failed, so this control is a retry rather than a first run. */
  retry: boolean;
  onRequested: () => void;
  onFailed: () => void;
}): JSX.Element {
  const { mutation } = useRecalculate(caseId);
  // Not `mutation.isPending`. The header renders its own Recalculate for the same
  // case-wide command, and calling the same hook does *not* share observer state — each
  // call gets its own `useMutation`. Reading the shared mutation key instead is what
  // makes both controls go busy together; otherwise activating one leaves the other
  // looking idle and a second concurrent run is one Tab away.
  const busy = useRecalculationInFlight(caseId) || mutation.isPending;

  useEffect(() => {
    if (mutation.isError) onFailed();
  }, [mutation.isError, onFailed]);

  return (
    <div className="cw-issue-group__action">
      <button
        type="button"
        className="cw-button cw-button--secondary"
        aria-disabled={busy}
        onClick={() => {
          if (busy) return;
          // Only a flag, set synchronously while this component is certainly mounted.
          // The outcome is announced by the parent, which survives the queue emptying.
          onRequested();
          mutation.mutate();
        }}
      >
        {busy ? "Rechecking…" : retry ? "Try again" : "Recheck now"}
        {/* "Try again" has no antecedent in a screen reader's control list, and after a
            reload — the whole point of making the failure durable — there is no alert
            left to supply one. Same hidden-suffix pattern as Dismiss (2.4.6, 2.5.3). */}
        {busy ? null : (
          <span className="cw-visually-hidden"> — recheck your conclusions</span>
        )}
      </button>
      {/* Deliberately silent about whether anything changed. A server-side failure
          leaves the figures alone and the durable item below says so — but a timeout or
          a dropped response after the run committed lands here too, and there the
          conclusions moved. One sentence has to be true of both. */}
      {/* The single announcer for a failed recheck: assertive, so it lands first, and
          visible, so a sighted user is not left watching the button settle. The
          destination deliberately sets no polite message for this. */}
      {mutation.isError ? (
        <p role="alert" className="cw-case-header__error">
          That recheck didn’t finish. This list has been refreshed with what the server
          recorded — anything it did record is shown below.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Setting an issue aside.
 *
 * Only offered where the server marks the issue dismissible, and the server refuses
 * anything else with a domain error — the control's absence and the refusal are two
 * expressions of one rule, not a client-side convention.
 *
 * **Not optimistic.** Hiding the card immediately would show the item leaving the queue in
 * exactly the cases where the server refuses, which is the one thing a dismissal must not
 * do. The mutation itself is owned by the destination; this renders its state.
 */
function DismissAction({
  issue,
  onDismiss,
  state,
}: {
  issue: Issue;
  onDismiss: (issue: Issue) => void;
  state: { isPending: boolean; isError: boolean; variables?: string | undefined };
}): JSX.Element {
  const busy = state.isPending && state.variables === issue.id;
  const failed = state.isError && state.variables === issue.id;
  // Every card shares one mutation observer, and starting a second dismissal detaches it
  // from the first: the first card's callbacks never run, so its dismissal is never
  // announced, focus is never returned, and a failure renders no alert anywhere. Owning
  // the mutation in the parent fixed unmount, not supersession. One at a time.
  const blocked = state.isPending;

  return (
    <span className="cw-issue-card__dismiss">
      <button
        type="button"
        className="cw-action cw-action--muted"
        aria-disabled={blocked}
        onClick={() => (blocked ? undefined : onDismiss(issue))}
      >
        {busy ? "Dismissing…" : "Dismiss"}
        {/* Several cards can offer "Dismiss" at once, and a screen reader's control list
            strips the surrounding card. The hidden suffix names the target without
            replacing the visible label, so "click Dismiss" still matches (2.5.3). */}
        {busy ? null : <span className="cw-visually-hidden"> {issue.title}</span>}
      </button>
      {failed ? (
        <span role="alert" className="cw-issue-card__dismiss-error">
          We couldn’t dismiss “{issue.title}”. It is still open.
        </span>
      ) : null}
    </span>
  );
}

/**
 * Issues that are no longer open. Retained rather than deleted (Domain §36.6): a queue
 * that empties without trace makes a resolved problem indistinguishable from one that
 * never happened.
 */
function ResolvedHistory({ issues }: { issues: Issue[] }): JSX.Element {
  return (
    <section aria-labelledby="issue-history-heading">
      <h3
        id="issue-history-heading"
        className="cw-issue-group__heading cw-issue-history__heading"
      >
        Settled
      </h3>
      <ul className="cw-issue-history" role="list">
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
