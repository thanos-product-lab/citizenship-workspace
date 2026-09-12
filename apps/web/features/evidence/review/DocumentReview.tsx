"use client";

/**
 * The document review split view: the document on one side, what a model read out of it
 * on the other, and the decision a person makes about each field.
 *
 * **This screen is the trust boundary made operable.** Everything else in M8 keeps an
 * unreviewed proposal out of a trusted fact; here is where the review actually happens,
 * and where the design either survives contact with a person or does not.
 *
 * Three things worth knowing before reading the code:
 *
 * - **A high-risk field shows no proposed value and starts empty.** Not because this
 *   component hides it — because the API does not send it (`proposed_value` is `null`
 *   while a blind claim is pending). There is nothing here to leak, which is the point
 *   of putting the guarantee at the wire rather than in the markup.
 * - **The preview and the text panel are equivalents, not a primary and a fallback.**
 *   An embedded PDF is not reliably readable by a screen reader, and this screen asks
 *   the reader to *read the document*. Both are in the same tab order and neither is
 *   hidden from anyone.
 * - **The outcome is announced.** "Confirmed" and "Corrected" are different things that
 *   happened, and a user who cannot see the badge change must still hear which.
 */

import { ExtractedFieldReview, type RejectionOption } from "@cw/design-system";
import Link from "next/link";
import { useState, type JSX } from "react";

import {
  DocumentGone,
  useDocumentClaims,
  type ReviewClaim,
} from "./useDocumentClaims";
import { useDocumentPreview } from "./useDocumentPreview";
import { useDocumentText } from "./useDocumentText";
import {
  ReviewRefused,
  useReviewClaim,
  type RejectionCode,
} from "./useReviewClaim";

/**
 * What each claim type is called on screen.
 *
 * `travel.departure_date` is the domain's name for the field and the right thing to
 * store; it is not a thing to show anybody. A missing entry falls back to a humanised
 * form rather than rendering the key, so a claim type added on the server appears as
 * readable words here before this map catches up.
 */
const FIELD_LABELS: Record<string, string> = {
  "travel.departure_date": "Departure date",
  "travel.return_date": "Return date",
  "travel.origin": "Departing from",
  "travel.destination": "Arriving at",
  "travel.booking_reference": "Booking reference",
  "travel.traveller_name": "Traveller name",
};

/** RFC §10's reasons, in the words a person would use. */
const REJECTION_OPTIONS: readonly RejectionOption[] = [
  { value: "VALUE_NOT_PRESENT", label: "This is not on the document" },
  { value: "WRONG_FIELD", label: "That value belongs to a different field" },
  { value: "WRONG_DOCUMENT", label: "This is not about this document" },
  { value: "DUPLICATE", label: "This repeats something already recorded" },
  { value: "AMBIGUOUS", label: "The document is not clear enough to say" },
  { value: "OTHER", label: "Something else" },
];

/**
 * Format guidance with **no usable date in it**, and that is deliberate.
 *
 * The first version read "for example 4 May 2026", which put a plausible date on screen
 * beside the empty box — the exact shape of the failure blind entry exists to prevent,
 * arriving through the help text rather than through a pre-filled input. Someone in a
 * hurry types the example. Caught by the test that scans the whole rendered panel for
 * anything date-shaped, which is why that test looks at the panel and not at the control.
 *
 * The slashed form stays, because it is the one being refused rather than offered, and
 * naming it is what stops the refusal reading as arbitrary.
 */
const DATE_HINT =
  "Type it as the document writes it. Use the month's name — day, month, year — or the " +
  "form YYYY-MM-DD. A slashed date such as 03/04/2025 can be read two ways, so it is refused.";

interface FieldState {
  entered: string;
  correcting: boolean;
  rejecting: boolean;
  reason: string;
  error: string | null;
}

const BLANK: FieldState = {
  entered: "",
  correcting: false,
  rejecting: false,
  reason: REJECTION_OPTIONS[0]!.value,
  error: null,
};

export function DocumentReview({
  caseId,
  evidenceItemId,
  documentName,
}: {
  caseId: string;
  evidenceItemId: string;
  documentName: string;
}): JSX.Element {
  const claims = useDocumentClaims(caseId, evidenceItemId);
  const preview = useDocumentPreview(caseId, evidenceItemId);
  const [pane, setPane] = useState<"document" | "text">("document");
  const text = useDocumentText(caseId, evidenceItemId, pane === "text");
  const review = useReviewClaim(caseId);

  const [fields, setFields] = useState<Record<string, FieldState>>({});
  // `{ text, seq }` rather than a bare string. React bails out of a state update when the
  // value is unchanged, so confirming the *same* value on the same-named field of a
  // second journey wrote an identical string, mutated nothing, and was announced to
  // nobody. Rejections are the worse case: their wording carries no value at all, so
  // every rejection after the first was silent.
  const [announcement, setAnnouncement] = useState({ text: "", seq: 0 });
  const announce = (text: string) =>
    setAnnouncement((prev) => ({ text, seq: prev.seq + 1 }));

  const stateFor = (claimId: string): FieldState => fields[claimId] ?? BLANK;
  const patch = (claimId: string, change: Partial<FieldState>) =>
    setFields((current) => ({
      ...current,
      [claimId]: { ...(current[claimId] ?? BLANK), ...change },
    }));

  async function decide(
    claim: ReviewClaim,
    input: Parameters<typeof review.mutateAsync>[0],
  ) {
    patch(claim.id, { error: null });
    try {
      const outcome = await review.mutateAsync(input);
      // Refetched *before* announcing, deliberately. M7 shipped a bug where a refetch
      // overwrote a live-region message 38ms after it was set, so a screen reader never
      // said the thing had happened; announcing once the DOM has settled is what stops
      // this being that again.
      await claims.refetch();
      patch(claim.id, { entered: "", correcting: false, rejecting: false });
      announce(
        describeOutcome(fieldLabel(claim), outcome.decision, outcome.value),
      );
      // Focus follows the field. The control the user just activated is unmounted the
      // moment the claim settles, which dropped focus to `<body>`: a keyboard user lost
      // their place on every save and had to tab from the top of the page past every
      // decided field to reach the next open one, and a screen-reader user's virtual
      // cursor jumped to the top with only the announcement to go on. Four fields, four
      // times. The deletion flow solved the same problem the same way in M7.
      requestAnimationFrame(() =>
        document.getElementById(`claim-${claim.id}-card`)?.focus(),
      );
    } catch (error) {
      if (error instanceof ReviewRefused) {
        patch(claim.id, { error: error.message });
        // Focus back to the box, not left on Save. The ambiguous-date refusal asks the
        // user to *retype*, and leaving them on the button means finding their way back
        // to a field that still holds the value that was refused. `TravelRecordForm`
        // takes the same route for the same reason.
        requestAnimationFrame(() =>
          document.getElementById(`claim-${claim.id}`)?.focus(),
        );
        if (error.code === "CLAIM_ALREADY_REVIEWED") {
          // Somebody else — another tab, usually — decided this claim. Refetch so the
          // field stops offering to decide it again, and **say so**: the refetch settles
          // the field, which takes the error message down with it, so without this the
          // user clicks Save, watches the field turn into a decision, and reasonably
          // concludes theirs was the one recorded. It was not.
          void claims
            .refetch()
            .then(() =>
              announce(
                `${fieldLabel(claim)} had already been decided, so what you typed was not recorded.`,
              ),
            );
          return;
        }
        return;
      }
      patch(claim.id, { error: "That could not be recorded. Try again." });
    }
  }

  if (claims.isPending) {
    return (
      <p role="status" style={{ color: "var(--cw-text-muted)" }}>
        Loading what we read from this document…
      </p>
    );
  }

  if (claims.error instanceof DocumentGone) {
    return (
      <div role="alert" className="cw-empty">
        <p>
          This document is no longer in your case, so there is nothing left to
          confirm.
        </p>
        <Link
          className="cw-button cw-button--secondary"
          href={`/cases/${caseId}/evidence`}
        >
          Back to your documents
        </Link>
      </div>
    );
  }

  if (claims.error) {
    return (
      <div role="alert" className="cw-empty">
        <p>
          We could not load what this document proposed. That is a problem
          reaching the server, not a statement about your document — nothing has
          changed.
        </p>
        <button
          type="button"
          className="cw-button"
          onClick={() => void claims.refetch()}
        >
          Try again
        </button>
      </div>
    );
  }

  const items = claims.data ?? [];
  const open = items.filter((claim) => claim.decision === null);
  const journeys = groupByJourney(items);

  return (
    <div>
      <div aria-live="polite" className="cw-visually-hidden">
        {announcement.text}
      </div>

      <div className="cw-review">
        <section className="cw-review__pane" aria-label="The document">
          <div
            className="cw-review__tabs"
            role="group"
            aria-label="How to read the document"
          >
            <button
              type="button"
              className={`cw-button ${pane === "document" ? "" : "cw-button--secondary"}`}
              aria-pressed={pane === "document"}
              aria-controls="review-pane-body"
              onClick={() => setPane("document")}
            >
              Document
            </button>
            <button
              type="button"
              className={`cw-button ${pane === "text" ? "" : "cw-button--secondary"}`}
              aria-pressed={pane === "text"}
              aria-controls="review-pane-body"
              onClick={() => setPane("text")}
            >
              Text
            </button>
            {preview.data?.url ? (
              // The frame renders an A4 page at roughly half scale — the shell caps
              // content at 52rem, so each pane is about 400px at every desktop width, and
              // 10pt body text lands around 5px tall. Not a WCAG failure (the browser's
              // viewer has its own zoom, and the Text pane is the same content at full
              // size), but the task on this screen is *read the date off the document*,
              // and offering no way to see it properly is the wrong place to be stingy.
              //
              // `rel="noreferrer"`: this is a signed URL, and threat model §6.4 keeps
              // those out of anywhere they can be logged — a `Referer` header is exactly
              // that.
              <a
                className="cw-button cw-button--secondary"
                href={preview.data.url}
                target="_blank"
                rel="noreferrer"
              >
                Open full size
                <span className="cw-visually-hidden"> in a new tab</span>
              </a>
            ) : null}
          </div>

          {/* The id the two toggles name. Without it nothing tells a screen reader that
              pressing "Text" changed something elsewhere on the page — focus stays on the
              button and the user has to go looking for what moved. */}
          <div id="review-pane-body">
            {pane === "document" ? (
              preview.data?.url ? (
                <iframe
                  className="cw-review__frame"
                  src={preview.data.url}
                  title={`${documentName} — the document as uploaded`}
                />
              ) : (
                <p role="status" className="cw-review__text">
                  {preview.isPending
                    ? "Opening the document…"
                    : "The document could not be opened just now. The fields on the right " +
                      "still work, and switching to Text will show what was read from it."}
                </p>
              )
            ) : text.isPending ? (
              <p role="status" className="cw-review__text">
                Loading the text…
              </p>
            ) : text.data ? (
              <>
                {/* Two caps can stop a read and only one shows in the page counts: a
                    character ceiling can cut the last page in half while `pages_read`
                    and `page_count` still agree. Keyed on the counts alone, this panel
                    showed a silently shortened document to someone who had been asked to
                    read it and type what it says. */}
                {text.data.pages_read < text.data.page_count ||
                text.data.truncated ? (
                  <p role="status" className="cw-field-review__hint">
                    {text.data.pages_read < text.data.page_count
                      ? `Only the first ${text.data.pages_read} of ${text.data.page_count} pages were read, so anything after that is not shown here.`
                      : "This document was longer than we could read, so the end of it is not shown here."}
                  </p>
                ) : null}
                <div
                  className="cw-review__text"
                  tabIndex={0}
                  role="region"
                  aria-label="Document text"
                >
                  {text.data.content}
                </div>
              </>
            ) : (
              <p role="status" className="cw-review__text">
                There is no text to show: this looks like a scan or a photo, so
                a parser found nothing to read. Use the Document view instead.
              </p>
            )}
          </div>
        </section>

        <section
          className="cw-review__pane"
          aria-label="What we read from this document"
        >
          <p role="status">
            {items.length === 0
              ? "Nothing here needs your decision."
              : open.length === 0
                ? `All ${items.length} values have been decided.`
                : `${open.length} of ${items.length} values still need your decision.`}
          </p>

          {journeys.map(([journey, group]) => (
            <div className="cw-review__journey" key={journey}>
              {journeys.length > 1 ? (
                // Only when there is more than one. A booking with a single journey has
                // nothing to disambiguate, and "Journey 1" on its own is a heading that
                // implies a Journey 2 the user should be looking for.
                <h2 className="cw-review__journey-heading">
                  Journey {journey + 1}
                </h2>
              ) : null}
              {group.map((claim) => {
                const state = stateFor(claim.id);
                return (
                  <ExtractedFieldReview
                    key={claim.id}
                    id={`claim-${claim.id}`}
                    label={fieldLabel(claim)}
                    blind={claim.requires_blind_entry}
                    proposedValue={claim.proposed_value}
                    decision={
                      claim.decision
                        ? {
                            decision: claim.decision.decision,
                            reviewMode: claim.decision.review_mode,
                            value: claim.decision.value,
                            reasonCode: claim.decision.reason_code,
                            reviewedAt: claim.decision.reviewed_at,
                          }
                        : null
                    }
                    entered={state.entered}
                    onEnteredChange={(entered) => patch(claim.id, { entered })}
                    onSubmit={() =>
                      void (function submit() {
                        // An empty blind field is not a date the server failed to read —
                        // it is a form that was not filled in, and posting it produced
                        // "that date could be read more than one way" about nothing at
                        // all. Answered here rather than at the boundary because the
                        // server genuinely cannot tell an empty string from an unreadable
                        // one, and only the client knows the user simply has not typed yet.
                        if (claim.requires_blind_entry && !state.entered.trim()) {
                          patch(claim.id, {
                            error: "Type the date as the document writes it, then save.",
                          });
                          return;
                        }
                        void decide(claim, {
                        claimId: claim.id,
                        // A blind field sends only what was typed: there is no field in
                        // the request for asserting which decision it was, so the server
                        // works it out from the entry.
                        ...(claim.requires_blind_entry
                          ? { enteredValue: state.entered }
                          : state.correcting
                            ? {
                                decision: "CORRECT" as const,
                                enteredValue: state.entered,
                              }
                            : { decision: "CONFIRM" as const }),
                        });
                      })()
                    }
                    onReject={(reasonCode) =>
                      void decide(claim, {
                        claimId: claim.id,
                        decision: "REJECT" as const,
                        reasonCode: reasonCode as RejectionCode,
                      })
                    }
                    correcting={state.correcting}
                    onCorrectingChange={(correcting) =>
                      patch(claim.id, {
                        correcting,
                        // Seeded with the proposal, and only here: this is a low-risk
                        // field the user has explicitly asked to change, so starting from
                        // what was read saves retyping a booking reference. A blind field
                        // never reaches this branch.
                        entered: correcting ? (claim.proposed_value ?? "") : "",
                      })
                    }
                    rejecting={state.rejecting}
                    onRejectingChange={(rejecting) =>
                      patch(claim.id, { rejecting })
                    }
                    rejectionOptions={REJECTION_OPTIONS}
                    rejectionReason={state.reason}
                    onRejectionReasonChange={(reason) =>
                      patch(claim.id, { reason })
                    }
                    error={state.error}
                    // **This claim's** decision, not any decision on the page. One
                    // mutation hook serves every field, so `review.isPending` alone put
                    // every other field on the screen into a busy state while one was
                    // saving — a user who moved on to the next field found it refusing
                    // keystrokes for no reason they could see.
                    busy={
                      review.isPending && review.variables?.claimId === claim.id
                    }
                    hint={claim.requires_blind_entry ? DATE_HINT : undefined}
                    context={
                      journeys.length > 1 ? `Journey ${journey + 1}` : undefined
                    }
                  />
                );
              })}
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function fieldLabel(claim: ReviewClaim): string {
  return FIELD_LABELS[claim.claim_type] ?? humanise(claim.claim_type);
}

function humanise(claimType: string): string {
  const field = claimType.split(".").pop() ?? claimType;
  const words = field.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Journeys in order, each with its fields in the order the API returned them. */
function groupByJourney(claims: ReviewClaim[]): [number, ReviewClaim[]][] {
  const groups = new Map<number, ReviewClaim[]>();
  for (const claim of claims) {
    const bucket = groups.get(claim.journey_index) ?? [];
    bucket.push(claim);
    groups.set(claim.journey_index, bucket);
  }
  return [...groups.entries()].sort(([a], [b]) => a - b);
}

/**
 * What to say out loud once a decision lands.
 *
 * Confirmed and corrected are different outcomes and the difference is the whole point:
 * a user who typed what they read and got "corrected" has just learned the model read
 * the document differently, which is information they need and which the badge alone
 * gives only to someone who can see it.
 */
function describeOutcome(
  label: string,
  decision: string,
  value: string | null,
): string {
  if (decision === "REJECT")
    return `${label}: rejected. Nothing was recorded from it.`;
  if (decision === "CORRECT") {
    return `${label}: corrected to ${value}. That differs from what we read, and yours is what was recorded.`;
  }
  return `${label}: confirmed as ${value}. That matches what we read.`;
}
