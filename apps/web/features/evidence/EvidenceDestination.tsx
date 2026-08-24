"use client";

import { type JSX, useEffect, useRef, useState } from "react";

import { EvidenceState } from "@cw/design-system";

import { cardStyle, errorTextStyle, linkButtonStyle, secondaryButtonStyle } from "@/components/ui";


import { CATEGORY_LABELS, formatBytes, type EvidenceItem } from "./library";
import { UploadDocument } from "./UploadDocument";
import { useEvidence } from "./useEvidence";
import { useRetryProcessing } from "./useRetryProcessing";

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
  const retry = useRetryProcessing(caseId);

  // The retry button disappears on success, taking keyboard focus to <body> with it, so
  // focus is parked on the heading once the refetch settles.
  useEffect(() => {
    if (returnFocus && status !== "pending" && !isFetching) {
      setReturnFocus(false);
      headingRef.current?.focus();
    }
  }, [returnFocus, status, isFetching]);

  // Announce the library's shape once it settles. `role="status"` mounted with its text
  // already in it does not announce reliably, so both the loaded and the empty case are
  // routed through the live region that is always mounted below.
  const itemCount = data?.items.length;
  useEffect(() => {
    if (status !== "success" || itemCount === undefined) return;
    setAnnouncement(
      itemCount === 0
        ? "No documents yet."
        : `${itemCount} document${itemCount === 1 ? "" : "s"}.`,
    );
  }, [status, itemCount]);

  return (
    <section aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" ref={headingRef} tabIndex={-1} className="cw-case-data__heading">
        Evidence
      </h2>
      <p className="cw-case-data__note">
        Documents you have uploaded to support this case. Nothing here has been read or
        checked yet, so every figure in your assessment still rests on dates you entered
        yourself.
      </p>

      <div aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </div>

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
              setAnnouncement(
                `${name} uploaded. It is listed as Uploaded, and nothing has read it yet.`,
              )
            }
          />

          {data.items.length === 0 ? (
            <p style={{ color: "var(--cw-text-muted)" }} data-testid="evidence-empty">
              No documents yet. Uploading one stores it privately against this case.
            </p>
          ) : (
            <EvidenceTable
              items={data.items as EvidenceItem[]}
              busy={isFetching}
              retryingId={retry.isPending ? retryingId : null}
              onRetry={(id) => {
                setRetryingId(id);
                setAnnouncement("Reading that document again.");
                retry.mutate(id);
              }}
            />
          )}
        </>
      ) : null}
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
    return "This looks like a scan or a photo, so there was no text to read.";
  }
  return null;
}

function describeText(item: EvidenceItem): string {
  if (item.character_count === null || item.character_count === undefined) {
    return formatBytes(item.size_bytes);
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
  busy,
  onRetry,
  retryingId,
}: {
  items: EvidenceItem[];
  busy: boolean;
  onRetry: (id: string) => void;
  retryingId: string | null;
}): JSX.Element {
  return (
    <div className="cw-trips-wrap">
      <table className="cw-trips" aria-busy={busy || undefined}>
        <caption className="cw-trips__caption">
          Documents uploaded to this case, newest first. Nothing has read them yet.
        </caption>
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">Type</th>
            <th scope="col">State</th>
            <th scope="col">Size</th>
            <th scope="col">Added</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.id}>
              <th scope="row" className="cw-trips__destination">
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
              <td>{CATEGORY_LABELS[item.category] ?? item.category}</td>
              <td>
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
                    aria-disabled={retryingId === item.id}
                    onClick={() => {
                      if (retryingId === item.id) return;
                      onRetry(item.id);
                    }}
                  >
                    {retryingId === item.id ? "Reading again…" : "Read it again"}
                    <span className="cw-visually-hidden"> — {item.display_name}</span>
                  </button>
                ) : null}
              </td>
              <td>{describeText(item)}</td>
              <td>{formatDate(item.uploaded_at)}</td>
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
