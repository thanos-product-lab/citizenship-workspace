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

import {
  groupHeading,
  type Issue,
  type IssueGroup,
  type RecheckTaskView,
} from "./groups";
import {
  AdoptionRefused,
  useAdoptDocumentDates,
} from "./useAdoptDocumentDates";
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
  const adopt = useAdoptDocumentDates(caseId);
  const [recheckRequested, setRecheckRequested] = useState(false);
  // What the last update left, shown until the next one. The live region says it too, but
  // only a screen reader hears that; a sighted user saw the list change and was told
  // nothing about what the change meant.
  const [outcome, setOutcome] = useState<string | null>(null);
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
    if (
      !recheckRequested ||
      recheckInFlight ||
      isFetching ||
      status === "pending"
    )
      return;

    // Said in actions, the unit the navigation counts (ADR-0033), rather than in issues
    // resolved: eight stale issues clearing is one thing done, and "8 issues resolved"
    // described bookkeeping the user never saw.
    const remaining = queue?.action_count ?? 0;
    const message =
      remaining === 0
        ? "Assessment updated. Nothing needs your action."
        : `Assessment updated. ${remaining === 1 ? "1 action remains" : `${remaining} actions remain`}.`;
    setAnnouncement(message);
    setOutcome(message);
    setRecheckRequested(false);
    setReturnFocus(true);
  }, [queue?.action_count, recheckRequested, recheckInFlight, isFetching, status]);

  return (
    <section aria-labelledby="issues-heading">
      <h2
        id="issues-heading"
        className="cw-case-data__heading"
        ref={headingRef}
        tabIndex={-1}
      >
        Issues
      </h2>
      <p className="cw-case-data__note">
        Problems with your information, and results waiting to be rechecked. Each
        requirement’s result is on Requirements.
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
              We couldn’t load your issues, so we can’t tell whether anything needs
              your attention.
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
          {outcome ? <p className="cw-issue-queue__outcome">{outcome}</p> : null}

          {openCount === 0 ? (
            <SettledStatement caseId={caseId} />
          ) : (
            <>
              <QueueSummary
                actions={queue.action_count}
                awareness={queue.awareness_count}
              />
              <NotRecheckedNote queue={queue} />
            </>
          )}

          {queue.recheck ? (
            <RecheckTask
              caseId={caseId}
              task={queue.recheck}
              onRequested={() => {
                // Say something now: the label changing to "Updating…" and
                // `aria-disabled` going true are both silent to a screen reader, so
                // without this the user gets no feedback for the length of the request.
                setOutcome(null);
                setAnnouncement("Updating your assessment.");
                setRecheckRequested(true);
              }}
              onFailed={() => {
                // Clear the flag but say nothing here. `RecheckAction` renders a
                // `role="alert"` for the same failure, which is assertive and lands first;
                // a polite message behind it repeats the same fact in slightly different
                // words and sounds like a second event. One failure, one announcer.
                //
                // Clearing matters on its own: a failure refetches the queue, which adds
                // the processing-failure item, so the count moves, and a still-armed
                // update would report "Assessment updated" over one that did not finish.
                setAnnouncement("");
                setRecheckRequested(false);
              }}
            />
          ) : null}

          {queue.groups.map((group) => (
            <IssueGroupSection
              key={group.action_group}
              caseId={caseId}
              group={group}
              adoptState={adopt}
              onAdopt={(issue) => {
                adopt.mutate(issue.affected_object_id, {
                  onSuccess: () => {
                    // Says what changed *and* what has not. The figures do not move until
                    // a recalculation runs, and a message that stopped at "updated" would
                    // let a user read the unchanged total as confirmation that adopting
                    // the document made no difference.
                    setAnnouncement(
                      `The dates from the document were applied to your trip. ` +
                        `Update your assessment to recheck your totals.`,
                    );
                    setReturnFocus(true);
                  },
                });
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

          {queue.history.length > 0 ? (
            <ResolvedHistory issues={queue.history} />
          ) : null}
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
  queue: { recheck?: { checks: unknown[] } | null };
}): JSX.Element | null {
  if (!queue.recheck || queue.recheck.checks.length === 0) return null;
  return (
    <p className="cw-issue-queue__caveat">
      Some of these are from before your last change and have not been rechecked yet.
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
        No problems were found in your information, but some results are out of date.
        Update your assessment to recheck them.
      </p>
    );
  }
  return (
    <p className="cw-issue-queue__settled">
      Nothing needs your attention. Your results are up to date and no problems were
      found in your information.
    </p>
  );
}

/**
 * How much of the queue is the user's to do, and how much is only to know. Both numbers
 * come from the server (ADR-0033), the same `action_count` the navigation shows, so the
 * two cannot disagree.
 */
function QueueSummary({
  actions,
  awareness,
}: {
  actions: number;
  awareness: number;
}): JSX.Element {
  const todo =
    actions === 0
      ? "Nothing needs your action."
      : `${actions === 1 ? "1 thing needs" : `${actions} things need`} your action.`;
  const notes =
    awareness === 0
      ? ""
      : ` ${awareness === 1 ? "1 note" : `${awareness} notes`} for information.`;
  return <p className="cw-issue-queue__summary">{todo + notes}</p>;
}

/**
 * Every stale conclusion, and a failed update if there is one, as the single task they are.
 *
 * Four cards for one button read as four jobs, and the button sat above them rather than
 * with the explanation. The stored issues are unchanged (ADR-0015): each is still its own
 * row, resolves on its own and appears on its own in the history below. The sentences are
 * the server's, like every other issue's.
 */
function RecheckTask({
  caseId,
  task,
  onRequested,
  onFailed,
}: {
  caseId: string;
  task: RecheckTaskView;
  onRequested: () => void;
  onFailed: () => void;
}): JSX.Element {
  const headingId = "issue-group-RECHECK_CONCLUSIONS";
  return (
    <section className="cw-issue-group" aria-labelledby={headingId}>
      <div className="cw-issue-group__head">
        <h3 id={headingId} className="cw-issue-group__heading">
          {groupHeading("RECHECK_CONCLUSIONS")}
        </h3>
      </div>
      <IssueCard
        titleId="issue-title-recheck"
        headingLevel={4}
        title={task.title}
        severity="ACTION_REQUIRED"
        body={task.body}
        impact={task.impact}
        details={
          task.checks.length > 0 ? (
            <ul aria-label="Results this update rechecks">
              {task.checks.map((check) => (
                <li key={check.issue_id}>
                  <a
                    className="cw-issue-card__link"
                    href={`/cases/${caseId}/requirements/${encodeURIComponent(check.requirement_key)}`}
                  >
                    {check.requirement_title}
                  </a>
                </li>
              ))}
            </ul>
          ) : undefined
        }
        actions={
          <RecheckAction
            caseId={caseId}
            retry={task.failed}
            onRequested={onRequested}
            onFailed={onFailed}
          />
        }
      />
    </section>
  );
}

function IssueGroupSection({
  caseId,
  group,
  onDismiss,
  dismissState,
  onAdopt,
  adoptState,
}: {
  caseId: string;
  group: IssueGroup;
  onDismiss: (issue: Issue) => void;
  dismissState: {
    isPending: boolean;
    isError: boolean;
    variables?: string | undefined;
  };
  onAdopt: (issue: Issue) => void;
  adoptState: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    variables?: string | undefined;
  };
}): JSX.Element {
  const headingId = `issue-group-${group.action_group}`;
  return (
    <section className="cw-issue-group" aria-labelledby={headingId}>
      <div className="cw-issue-group__head">
        <h3 id={headingId} className="cw-issue-group__heading">
          {groupHeading(group.action_group)}
        </h3>
        {/* A count, never a fraction: "3 of 9" is a completion measure by another name. */}
        <span className="cw-issue-group__count">
          {group.issues.length === 1
            ? "1 item"
            : `${group.issues.length} items`}
        </span>
      </div>

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
                issue.issue_type === "CONFLICTING_CLAIMS" ? (
                  <AdoptAction
                    issue={issue}
                    onAdopt={onAdopt}
                    state={adoptState}
                  />
                ) : issue.dismissibility === "DISMISSIBLE" ? (
                  <DismissAction
                    issue={issue}
                    onDismiss={onDismiss}
                    state={dismissState}
                  />
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

  if (issue.affected_object_type === "Evidence") {
    // The Evidence destination owns the library, and there is no per-document route. A
    // duplicate item without this rendered no footer link at all — the user was told two
    // of their files match and given no way to go and look at them.
    return (
      <a className="cw-issue-card__link" href={`/cases/${caseId}/evidence`}>
        Open your documents
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
        {/* One name for the one command, as in the case header (ADR-0033). */}
        {busy ? "Updating…" : retry ? "Try again" : "Update assessment"}
        {/* "Try again" has no antecedent in a screen reader's control list, and after a
            reload — the whole point of making the failure durable — there is no alert
            left to supply one. Same hidden-suffix pattern as Dismiss (2.4.6, 2.5.3). */}
        {busy || !retry ? null : (
          <span className="cw-visually-hidden"> to update your assessment</span>
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
          The update didn’t finish. This list shows what was saved.
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
function AdoptAction({
  issue,
  onAdopt,
  state,
}: {
  issue: Issue;
  onAdopt: (issue: Issue) => void;
  state: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    variables?: string | undefined;
  };
}): JSX.Element {
  const busy = state.isPending && state.variables === issue.affected_object_id;
  const failed = state.isError && state.variables === issue.affected_object_id;
  // One at a time, for the reason `DismissAction` records: every card shares one mutation
  // observer, and starting a second adoption detaches the first — whose success would then
  // be announced nowhere and whose failure would render no alert.
  const blocked = state.isPending;
  const hintId = `adopt-hint-${issue.id}`;

  return (
    <span className="cw-issue-card__dismiss">
      <button
        type="button"
        className="cw-action"
        aria-disabled={blocked}
        // The alternative is read *with* the control, not merely printed beside it. A
        // screen-reader user moving by control hears only the button's name, so without
        // this they would never learn there is another way to resolve a conflict — and the
        // one control on offer applies the document, which is the wrong answer whenever
        // the document is not about this trip. Verbose, and worth it: it is announced at
        // the moment the user is deciding whether to press.
        aria-describedby={hintId}
        onClick={() => (blocked ? undefined : onAdopt(issue))}
      >
        {busy ? "Applying…" : "Use the dates from the document"}
        {/* Several cards can offer this at once, and a screen reader's control list strips
            the surrounding card. The hidden suffix names the trip without replacing the
            visible label, so "click Use the dates…" still matches (2.5.3). */}
        {busy ? null : (
          <span className="cw-visually-hidden"> for {issue.title}</span>
        )}
      </button>
      {/* The other direction takes no code and no button: if the record is right, the
          document is not about this trip or the model misread it, and detaching it or
          rejecting the value are both already commands. Saying so beats a third control
          that would have to invent a state where two sources disagree and nothing is
          wrong. */}
      <span className="cw-issue-card__dismiss-hint" id={hintId}>
        If your record is right, detach the document from this trip or reject
        the value where you confirmed it.
      </span>
      {failed ? (
        <span role="alert" className="cw-issue-card__dismiss-error">
          {state.error instanceof AdoptionRefused &&
          state.error.code === "NO_CONFLICT_TO_RESOLVE"
            ? "Nothing on this trip disagrees with a document any more, so there was nothing to apply."
            : `We couldn’t apply those dates to “${issue.title}”. Nothing has changed.`}
        </span>
      ) : null}
    </span>
  );
}

function DismissAction({
  issue,
  onDismiss,
  state,
}: {
  issue: Issue;
  onDismiss: (issue: Issue) => void;
  state: {
    isPending: boolean;
    isError: boolean;
    variables?: string | undefined;
  };
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
        {busy ? null : (
          <span className="cw-visually-hidden"> {issue.title}</span>
        )}
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
              {issue.resolved_at
                ? ` · ${formatDateTime(issue.resolved_at)}`
                : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
