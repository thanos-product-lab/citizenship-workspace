"use client";

import { type JSX, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import {
  EvidenceState,
  evidenceProcessingTokens,
  toEvidenceProcessingState,
} from "@cw/design-system";

import { cardStyle, errorTextStyle, linkButtonStyle, secondaryButtonStyle } from "@/components/ui";


import {
  CATEGORY_LABELS,
  TERMINAL_PROCESSING_STATES,
  type EvidenceItem,
} from "./library";
import { UploadDocument } from "./UploadDocument";
import { useEvidence } from "./useEvidence";
import { ConfirmDialog } from "@/components/ConfirmDialog";

import { useDeleteEvidence } from "./useDeleteEvidence";
import { useRetryProcessing, type RetryRefusal } from "./useRetryProcessing";

/**
 * How long to wait after moving focus before writing an outcome into the live region.
 *
 * Long enough that the focus announcement has claimed its turn, short enough that the
 * outcome still reads as a response to what the user just did. Not tuned against a
 * specific screen reader — the ordering is what matters, and any positive delay puts the
 * region change after the focus event rather than in the same tick as it.
 */
const ANNOUNCE_AFTER_FOCUS_MS = 150;

/**
 * The Evidence destination: the documents this case holds, and what has been done to them.
 *
 * Three decisions worth stating.
 *
 * **This is not a file manager.** UI/UX §9.1 asks each document to show how it contributes
 * to the case — what it supports, what was extracted, what needs confirming. In slice 1
 * none of that exists yet, and the honest version of that table is a column that says so
 * rather than one that is blank. "Not yet read by anything" is a true statement about a
 * stored document; an empty "Supports" cell would read as "supports nothing", which is a
 * stronger claim than the product has earned.
 *
 * **An empty library is a real statement**, so a failed fetch must never render as one —
 * the same rule the issue queue follows. Silence and "you have uploaded nothing" must not
 * look alike.
 *
 * **No progress bar over the processing states.** A document's route through Domain §14.4
 * is not a fixed pipeline, and `AWAITING_CONFIRMATION` has no producer until M8. A stepper
 * would draw stages this build cannot reach.
 */
export function EvidenceDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data, status, refetch, isFetching } = useEvidence(caseId);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [announcement, setAnnouncement] = useState("");
  // State, not a ref: setting a ref does not re-render, so an effect keyed on it would
  // never run and focus would stay on the control that just unmounted. Copied from
  // IssuesDestination, where the same trap was found.
  const [returnFocus, setReturnFocus] = useState(false);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  // Which row to put focus back on once its retry control disappears. Pressing "Read it
  // again" moves the document to a non-retryable state, so the button unmounts and takes
  // keyboard focus to <body> with it — verified in the browser, and the third time this
  // codebase has been caught by a control destroyed by the success it reports. The row
  // itself is the right landing place: it keeps the user where they were and names what
  // they just acted on, where sending them to the page heading would not.
  const [returnFocusToRow, setReturnFocusToRow] = useState<string | null>(null);
  const retry = useRetryProcessing(caseId);
  const remove = useDeleteEvidence(caseId);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  // Rendered visibly, not only announced. `remove.isError` is not enough on its own: the
  // message has to name *which* document failed, and the mutation state is shared by
  // every row's control.
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deletingItem =
    deletingId && data?.items
      ? ((data.items as EvidenceItem[]).find((i) => i.id === deletingId) ?? null)
      : null;

  useEffect(() => {
    if (!returnFocusToRow || retry.isPending) return;
    const row = document.getElementById(`evidence-row-${returnFocusToRow}`);
    setReturnFocusToRow(null);
    row?.focus();
  }, [returnFocusToRow, retry.isPending]);

  // The retry button disappears on success, taking keyboard focus to <body> with it, so
  // focus is parked on the heading once the refetch settles.
  useEffect(() => {
    if (returnFocus && status !== "pending" && !isFetching) {
      setReturnFocus(false);
      headingRef.current?.focus();
    }
  }, [returnFocus, status, isFetching]);

  // Announce the library's shape when it *first* settles. `role="status"` mounted with its
  // text already in it does not announce reliably, so both the loaded and the empty case
  // are routed through the live region that is always mounted below.
  //
  // **First settle only, and that is the whole point.** Firing on every count change meant
  // this effect clobbered the outcome of whatever caused the change. Measured in Chrome:
  // deleting the only document put "Athens booking deleted." in the region and replaced it
  // with "No documents yet." **38 milliseconds later**, when the refetch landed. No screen
  // reader announces a polite message overwritten that fast, so the user was never told
  // the deletion happened at all.
  //
  // Every later change is the consequence of an action that announces its own, better
  // outcome — "X uploaded…", "X deleted.", "X: no text found". A count is what you say
  // when you have nothing more specific; here there always is something more specific.
  //
  // jsdom could not catch this: the test's GET mock returns the same library every time,
  // so the row never disappears and `itemCount` never changes.
  const itemCount = data?.items.length;
  const announcedShapeRef = useRef(false);
  useEffect(() => {
    if (status !== "success" || itemCount === undefined) return;
    if (announcedShapeRef.current) return;
    announcedShapeRef.current = true;
    setAnnouncement(
      itemCount === 0
        ? "No documents yet."
        : `${itemCount} document${itemCount === 1 ? "" : "s"}.`,
    );
  }, [status, itemCount]);

  // Announce *after* the focus move, not with it.
  //
  // A focus event commonly pre-empts a pending polite queue: set the region and move focus
  // in the same tick and the user hears "Evidence, heading level 2" instead of the outcome.
  // Moving focus first and letting the region change land afterwards gives the outcome its
  // own turn.
  //
  // Note this half is **not covered by a test**, and cannot be here: jsdom has no
  // assistive technology, so nothing in it can observe a focus event pre-empting a polite
  // queue. Removing the delay leaves the suite green. It is kept because the ordering is
  // free and the failure it avoids is invisible from this side — the sort of thing the
  // accessibility gate exists to insist on rather than prove.
  const announceAfterFocusMove = (message: string) => {
    window.setTimeout(() => setAnnouncement(message), ANNOUNCE_AFTER_FOCUS_MS);
  };

  // Announce a document *finishing*, once each.
  //
  // Polling rewrites the State cell every 1.5 seconds — Reading becomes Read, or No text
  // found, or Failed — and none of it reached the live region. A screen-reader user who
  // asked for a re-read was told it had started and then never told how it ended, which
  // is the half of the interaction that carries the answer.
  const settledRef = useRef<Map<string, string>>(new Map());
  const items = data?.items;
  useEffect(() => {
    if (!items) return;
    for (const item of items as EvidenceItem[]) {
      const previous = settledRef.current.get(item.id);
      settledRef.current.set(item.id, item.processing_status);
      if (previous === item.processing_status) continue;
      if (!TERMINAL_PROCESSING_STATES.has(item.processing_status)) continue;
      // Silent on the *first sighting of the row*, not on the first terminal status:
      // arriving on a page of settled rows is not five things happening, but a document
      // watched through Validating and Reading has been seen before, and its ending is
      // the half of the interaction that carries the answer. Recording every status —
      // not only terminal ones — is what tells those two apart. Skipping the non-terminal
      // ones made the row look newly arrived at the moment it settled, so the one
      // transition worth announcing was the one that stayed silent.
      if (previous !== undefined) setAnnouncement(`${item.display_name}: ${describeOutcome(item)}`);
    }
  }, [items]);

  return (
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" ref={headingRef} tabIndex={-1} className="cw-case-data__heading">
        Evidence
      </h2>
      <p className="cw-case-data__note">
        {/* Describes what this screen does, not what has happened on it. The first
            version said "nothing here has been read yet", which slice 3 made false; the
            second said "their text has been read", which is false on a case with no
            documents. A sentence about the capability is true in both. */}
        Documents you upload to support this case. Reading one extracts its text —
        nothing here is checked against your case, so every figure in your assessment
        still rests on dates you entered yourself.
      </p>

      <div aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </div>

      {deleteError ? (
        <p role="alert" style={{ margin: "0 0 var(--cw-space-4)", ...errorTextStyle }}>
          {deleteError} The document is still listed below and nothing about your case has
          changed.
        </p>
      ) : null}

      {status === "pending" ? (
        <p role="status" style={{ color: "var(--cw-text-muted)" }}>
          Loading your documents…
        </p>
      ) : null}

      {status === "error" ? (
        <div role="alert" style={{ ...cardStyle, display: "grid", gap: "var(--cw-space-3)" }}>
          <p style={{ margin: 0, ...errorTextStyle }}>
            Your documents could not be loaded, so this list is not a statement about what
            the case holds.
          </p>
          <div>
            {/* `aria-disabled` with a guard, never `disabled`: disabling the focused
                control drops the keyboard user to <body> mid-retry. Repeated presses
                would otherwise fire concurrent refetches with no feedback. */}
            <button
              type="button"
              style={secondaryButtonStyle}
              aria-disabled={isFetching}
              onClick={() => {
                if (isFetching) return;
                setReturnFocus(true);
                setAnnouncement("Retrying.");
                void refetch();
              }}
            >
              {isFetching ? "Retrying…" : "Try again"}
            </button>
          </div>
        </div>
      ) : null}

      {status === "success" ? (
        <>
          <UploadDocument
            caseId={caseId}
            supportedMediaTypes={data.supported_media_types ?? []}
            maxBytes={data.max_upload_bytes}
            onStarted={(name) => setAnnouncement(`Uploading ${name}…`)}
            onUploaded={(name) =>
              // Says where it went and what state it is in, not just that it happened —
              // and the trailing space differs from the "Uploading…" message above, so
              // two uploads of the same document still re-announce.
              // The caption and the page note were both corrected when reading landed;
              // this third copy was missed, and it is the only one no sighted user ever
              // sees. Reading starts seconds later and the table would contradict it.
              setAnnouncement(`${name} uploaded. Reading will start shortly.`)
            }
          />

          {data.items.length === 0 ? (
            <p style={{ color: "var(--cw-text-muted)" }} data-testid="evidence-empty">
              No documents yet. Uploading one stores it privately against this case.
            </p>
          ) : (
            <EvidenceTable
              items={data.items as EvidenceItem[]}
              retryingId={retryingId}
              // Every row shares one mutation observer, so a second retry while the
              // first is in flight silently abandons it — its button reverts and its
              // outcome is reported nowhere. Blocking all of them while any one is
              // pending is the same answer the issue queue reached for Dismiss.
              anyRetryPending={retry.isPending}
              onDelete={(id) => setDeletingId(id)}
              onRetry={(id) => {
                setRetryingId(id);
                setAnnouncement("Reading that document again.");
                // Focus is armed in `onSettled`, not here. Setting it synchronously lets
                // the effect fire before `isPending` is true and yank focus off the
                // button mid-press.
                retry.mutate(id, {
                  onSettled: () => setReturnFocusToRow(id),
                  onError: (refusal) => setAnnouncement(refusalMessage(refusal)),
                });
              }}
            />
          )}
        </>
      ) : null}
      <ConfirmDialog
        open={deletingItem !== null}
        // The document is named in the *title*, not only in the description. A screen
        // reader that announces a dialog's accessible name without its description — a
        // verbosity setting, or returning to the dialog after focus has moved — would
        // otherwise ask the user to confirm an irreversible action on an unnamed target.
        title={
          deletingItem ? `Delete ${deletingItem.display_name}?` : "Delete this document?"
        }
        description={
          deletingItem
            ? `${deletingItem.display_name} will be removed from this case and its contents ` +
              "destroyed. This cannot be undone. Any trip it supports will show as having " +
              "no document attached, and the travel-records check will need working out again."
            : ""
        }
        confirmLabel="Delete document"
        busyLabel="Deleting…"
        busy={remove.isPending}
        onConfirm={() => {
          if (!deletingId) return;
          const id = deletingId;
          const name = deletingItem?.display_name ?? "That document";
          setDeleteError(null);
          remove.mutate(id, {
            onSuccess: () => {
              flushSync(() => setDeletingId(null));
              headingRef.current?.focus();
              announceAfterFocusMove(`${name} deleted.`);
            },
            onError: () => {
              // A failed deletion used to be announced only into the visually-hidden live
              // region, so a sighted user saw the dialog close, the row still there, and
              // nothing saying why — believing an irreversible action had succeeded when
              // it had not. The failed upload next door has had a visible `role="alert"`
              // all along; the higher-stakes action had a hidden one.
              flushSync(() => {
                setDeletingId(null);
                setDeleteError(`${name} could not be deleted. Try again.`);
              });
              // Back to the control that failed, not to the section heading. The row still
              // exists on this path — unlike on success — so throwing the user to the top
              // of the section would make them Tab past the upload form and the whole
              // table to retry the thing they just attempted.
              document.getElementById(`delete-${id}`)?.focus();
            },
          });
        }}
        onCancel={() => {
          // Focus back to the control that opened it — the dialog owns focus while open,
          // and only the parent knows which row was pressed.
          const id = deletingId;
          flushSync(() => setDeletingId(null));
          document.getElementById(`delete-${id}`)?.focus();
        }}
      />
    </section>
  );
}

/**
 * What extraction found, in one short phrase.
 *
 * Counts and a flag — never the text. Full document content stays server-side until M8
 * has a review surface designed for it, so Tier-3 content does not sit in a response, in
 * the Next.js server's memory, or in an error reporter's breadcrumbs for the sake of a
 * cell that only has to say "this worked".
 */
/**
 * The one-line note beneath a state, or null where the state speaks for itself.
 *
 * A failure always carries its reason. "No text found" carries one too, because without
 * it the user cannot tell whether their document is broken — it is not; a scan simply
 * has no text layer, and reading one needs OCR, which is M8.
 */
function stateNote(item: EvidenceItem): string | null {
  if (item.failure_reason) return item.failure_reason;
  if (item.processing_status === "PARTIALLY_COMPLETED") {
    // Read from the token rather than repeated here: the same sentence written twice in
    // two packages is two sentences that can drift.
    return evidenceProcessingTokens.partially_completed.meaning;
  }
  return null;
}

/** What to say when a document finishes, for the live region. */
function describeOutcome(item: EvidenceItem): string {
  const note = stateNote(item);
  const state = toEvidenceProcessingState(item.processing_status);
  const label = state ? evidenceProcessingTokens[state].label : item.processing_status;
  return note ? `${label}. ${note}` : `${label}. ${describeText(item)}.`;
}

/** Why a retry was refused, in words. The server sends a code and the seconds. */
function refusalMessage(refusal: RetryRefusal): string {
  if (refusal.code === "EVIDENCE_RETRY_TOO_SOON") {
    const seconds = refusal.retryAfterSeconds ?? 30;
    return `That document was read very recently. You can try again in ${seconds} seconds.`;
  }
  if (refusal.code === "EVIDENCE_NOT_RETRYABLE") {
    return "That document cannot be read again. Uploading a different file may help.";
  }
  return "That document could not be sent to be read again.";
}

function describeText(item: EvidenceItem): string {
  if (item.character_count === null || item.character_count === undefined) {
    // No reading exists. Under a column headed "What we read", a file size answers a
    // question nobody asked, and mixing bytes with page counts down one column makes
    // both harder to scan — the state cell already says why.
    //
    // "yet" while the document is still moving: mid-extraction the row was otherwise
    // heard as "State: Reading. What we read: Not read."
    return TERMINAL_PROCESSING_STATES.has(item.processing_status) ? "Not read" : "Not read yet";
  }
  if (item.character_count === 0) return "No text";

  const pages = item.page_count ?? 0;
  const read = item.pages_read ?? pages;
  const pageLabel = pages === 1 ? "1 page" : `${pages} pages`;

  if (!item.text_truncated) return pageLabel;

  // `pages_read` comes from the server. The first version recomputed it in TypeScript
  // against a duplicated copy of the page cap, which was wrong twice over: changing the
  // server's cap would have made this lie, and when truncation was caused by the
  // *character* cap instead the arithmetic produced "10 pages, first 10 read" — a
  // sentence that is untrue and reassuring in the wrong direction.
  //
  // Where every page was opened but the read still stopped early, there is no page
  // arithmetic to state, so it says the honest general thing instead.
  return read < pages ? `${pageLabel}, first ${read} read` : `${pageLabel}, partly read`;
}

function EvidenceTable({
  items,
  onDelete,
  onRetry,
  retryingId,
  anyRetryPending,
}: {
  items: EvidenceItem[];
  onDelete: (id: string) => void;
  onRetry: (id: string) => void;
  retryingId: string | null;
  anyRetryPending: boolean;
}): JSX.Element {
  return (
    <div className="cw-trips-wrap">
      {/* No `aria-busy` from background polling. It tells assistive technology to
          suppress reporting changes inside the region, and flapping it twice a second
          at a table someone may be arrow-keying through is not what it is for. A
          user-initiated retry announces itself through the live region instead. */}
      <table className="cw-trips" role="table">
        <caption className="cw-trips__caption">
          Documents uploaded to this case, newest first. Reading a document extracts its
          text; it does not check anything against your case.
        </caption>
        <thead role="rowgroup">
          <tr role="row">
            {/* Explicit roles, matching `TravelHistory`: the ≤34rem reflow sets
                `display: block` on the table elements, which strips implicit table
                semantics in engines that do not special-case it. */}
            <th role="columnheader" scope="col">
              Document
            </th>
            <th role="columnheader" scope="col">
              Type
            </th>
            <th role="columnheader" scope="col">
              State
            </th>
            <th role="columnheader" scope="col">
              What we read
            </th>
            <th role="columnheader" scope="col">
              Added
            </th>
            <th role="columnheader" scope="col">
              <span className="cw-visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {items.map((item) => (
            <tr key={item.id} role="row">
              <th
                role="rowheader"
                scope="row"
                className="cw-trips__destination"
                id={`evidence-row-${item.id}`}
                // Focusable only programmatically: it is a landing place for focus that
                // would otherwise be dropped, not another stop in the tab order.
                tabIndex={-1}
              >
                {item.display_name}
                {item.original_filename ? (
                  <span
                    style={{
                      display: "block",
                      color: "var(--cw-text-muted)",
                      fontSize: "var(--cw-text-xs)",
                      fontWeight: "var(--cw-weight-regular)",
                    }}
                  >
                    {item.original_filename}
                  </span>
                ) : null}
              </th>
              <td role="cell">{CATEGORY_LABELS[item.category] ?? item.category}</td>
              <td role="cell">
                {/* No `withMeaning` here: the caption says it once. Repeating it per
                    row means a screen-reader user hears the same sentence twenty times
                    down a twenty-document library. */}
                <EvidenceState status={item.processing_status} size="sm" />
                {/* A document reading "Unsupported" with no reason is a dead end: the
                    user cannot tell whether to re-export the file, try a different one,
                    or give up. The sentence comes from the server so the client never
                    has to guess at a failure it did not observe. */}
                {/* A note, but only where the state does not explain itself.
                    The accessibility review objected to `withMeaning` repeating the same
                    sentence on every row — and it was right about that. This is the
                    narrower case: a *specific* state that leaves the user with a
                    question ("no text found" — is my document broken?), shown on the few
                    rows that need it rather than all of them. */}
                {stateNote(item) ? (
                  <span
                    style={{
                      display: "block",
                      color: "var(--cw-text-muted)",
                      fontSize: "var(--cw-text-xs)",
                      marginTop: "var(--cw-space-1)",
                    }}
                  >
                    {stateNote(item)}
                  </span>
                ) : null}
                {/* Offered only where the server says a retry could do something. The
                    rule lives on the server so the client cannot decide, for instance,
                    that an UNSUPPORTED file is worth trying again — it is not, and a
                    button that cannot work invites the user to keep pressing it. */}
                {item.can_retry ? (
                  <button
                    type="button"
                    style={{ ...linkButtonStyle, marginTop: "var(--cw-space-1)" }}
                    aria-disabled={anyRetryPending}
                    onClick={() => {
                      if (anyRetryPending) return;
                      onRetry(item.id);
                    }}
                  >
                    {anyRetryPending && retryingId === item.id
                      ? "Reading again…"
                      : "Read it again"}
                    {/* The suffix is dropped while busy: keeping it changes the
                        accessible name under a user whose focus is on the control. */}
                    {anyRetryPending ? null : (
                      <span className="cw-visually-hidden"> {item.display_name}</span>
                    )}
                  </button>
                ) : null}
              </td>
              <td role="cell">{describeText(item)}</td>
              <td role="cell">{formatDate(item.uploaded_at)}</td>
              {/* `cw-trips__actions` / `cw-action` give this a 44px target under the
                  narrow-width rules in components.css — the same treatment the *reversible*
                  "Remove" beside each document already gets. A bare inline button at text
                  height is a poor target for the one irreversible control in the product. */}
              <td role="cell" className="cw-trips__actions">
                <button
                  type="button"
                  id={`delete-${item.id}`}
                  className="cw-action"
                  style={linkButtonStyle}
                  onClick={() => onDelete(item.id)}
                >
                  <span aria-hidden="true">Delete</span>
                  {/* Named, because a column of bare "Delete" controls is indistinguishable
                      heard in sequence — and this is the one action in the library that
                      cannot be undone. */}
                  <span className="cw-visually-hidden">Delete {item.display_name}</span>
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A date, in the form the timeline already uses. */
function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
