import type { components } from "@cw/api-client";
import { evidenceProcessingTokens } from "@cw/design-system";

import { claimLabel } from "./review/claimLabels";

export type EvidenceItem = components["schemas"]["EvidenceResponse"];

/**
 * The supported document categories, in the order the user meets them.
 *
 * `OTHER` and `UNKNOWN` are in the domain enum (§14.2) but are not offered here: they can
 * be stored but cannot create a trusted fact without a review path, and offering a
 * category whose document can never support anything invites the user to file something
 * the product will not use.
 */
export const UPLOADABLE_CATEGORIES = [
  "IMMIGRATION_STATUS",
  "ENGLISH_LANGUAGE",
  "LIFE_IN_THE_UK",
  "TRAVEL_SUPPORT",
] as const;

export const CATEGORY_LABELS: Record<string, string> = {
  IMMIGRATION_STATUS: "Immigration status",
  ENGLISH_LANGUAGE: "English language",
  LIFE_IN_THE_UK: "Life in the UK",
  TRAVEL_SUPPORT: "Travel booking",
  OTHER: "Other",
  UNKNOWN: "Unknown",
};

/**
 * How the automatic analysis described a document, when it differs from the category the
 * user chose.
 *
 * Two extra values the upload form does not offer, because they are answers the *model*
 * can give and the user cannot: it read the document and could not tell (`AMBIGUOUS`), or
 * it read the document and it is not one of the four kinds this workspace handles
 * (`UNSUPPORTED`). Both are honest outcomes rather than failures.
 */
export const PROPOSED_CATEGORY_LABELS: Record<string, string> = {
  ...CATEGORY_LABELS,
  AMBIGUOUS: "Could not tell",
  UNSUPPORTED: "Not a supported document",
};

/**
 * What the analysis said, or null when there is nothing worth saying.
 *
 * Returns null when the analysis **agrees** with the user, and that is a deliberate
 * absence rather than an oversight. Printing "Analysis agrees" on every row of a
 * twenty-document library is twenty lines of noise a screen-reader user hears in full,
 * and it trains people to skim past the one row where the two differ — which is the only
 * row this is for.
 */
export function disagreement(item: EvidenceItem): string | null {
  const proposed = item.proposed_category;
  if (!proposed || proposed === item.category) return null;
  return PROPOSED_CATEGORY_LABELS[proposed] ?? proposed;
}

/** Sizes in the units a person uses, not bytes. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * States a document does not leave on its own.
 *
 * Mirrors `TERMINAL_PROCESSING_STATUSES` in `app/evidence/domain.py`, and the pairing is
 * asserted in `library.test.ts` against the generated schema — so a state added on the
 * server cannot silently become one the client polls forever, or one it stops watching
 * too early.
 *
 * `AWAITING_CONFIRMATION` is terminal *as far as the worker is concerned*: it waits for a
 * person, not for a process. It has no producer until M8 and appears here only so that
 * the day it arrives, the client stops polling rather than spinning against a document
 * that is waiting for the user sitting in front of it.
 */
export const TERMINAL_PROCESSING_STATES: ReadonlySet<string> = new Set([
  "COMPLETED",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "UNSUPPORTED",
  "AWAITING_CONFIRMATION",
]);

/**
 * States the worker moves a document through, where the next change arrives on its own.
 *
 * `UPLOADED` is in neither set, deliberately: it is where a document sits both *before*
 * validation starts and *after* it passes, and the client cannot tell those apart from
 * the state alone. Polling it forever would be a request every second-and-a-half for a
 * document that has arrived where it is going. See `pollInterval`.
 */
export const IN_FLIGHT_PROCESSING_STATES: ReadonlySet<string> = new Set([
  "VALIDATING",
  "EXTRACTING_TEXT",
  "ANALYSING",
]);

/** How often to re-ask while anything is still moving. */
export const POLL_INTERVAL_MS = 1500;

/**
 * How long to keep watching a freshly uploaded document before giving up on it moving.
 *
 * The awkward case this exists for: a document sits at `UPLOADED` both before and after
 * validation. Watching until it leaves `UPLOADED` would never stop, because passing
 * validation returns it there. So a recent upload is watched for a bounded window and
 * then left alone — the state it lands on is correct either way, and a manual refresh
 * costs the user nothing on a screen they are not staring at.
 */
export const SETTLE_WINDOW_MS = 15_000;

export function pollInterval(items: readonly EvidenceItem[], now: number): number | false {
  const moving = items.some((item) => IN_FLIGHT_PROCESSING_STATES.has(item.processing_status));
  if (moving) return POLL_INTERVAL_MS;

  const recent = items.some(
    (item) =>
      !TERMINAL_PROCESSING_STATES.has(item.processing_status) &&
      now - new Date(item.uploaded_at).getTime() < SETTLE_WINDOW_MS,
  );
  return recent ? POLL_INTERVAL_MS : false;
}

/**
 * What the person has decided about this document, or `null` where nothing was proposed.
 *
 * The processing state is the worker's ("Text read"), and it stays true after a review
 * while saying nothing about one. This is the other half: what is still open, named
 * where there is only one, and what was decided.
 *
 * A rejection is counted with the decisions, not with the work left. Rejecting a value
 * finishes it, and a row that read as needing attention because of one would be asking
 * the user to revisit a choice they already made.
 */
export function reviewSummary(item: EvidenceItem): string | null {
  const tally = reviewTally(item);
  if (!tally) return null;

  const decided = tally.decided.map(({ count, word }) => `${count} ${word}`).join(" · ");
  const parts = [tally.open, decided].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? `${parts.join(". ")}.` : null;
}

/** How a person decided about a proposed value. Each has its own glyph in the row. */
export type Decision = "confirmed" | "corrected" | "rejected";

export interface ReviewTally {
  /** What is still open, as a phrase: one value named, or several counted. */
  open: string | null;
  /** How many values are still open, for the review button's label. */
  pendingCount: number;
  /** Only the decisions that happened, in a fixed order. */
  decided: { word: Decision; count: number }[];
}

/**
 * `reviewSummary` as parts, so the row can give each its own glyph.
 *
 * Counts of named states, side by side, and never one over another: "4 confirmed · 1
 * rejected" is what happened, while "5 of 6 reviewed" would be a completion measure
 * (CLAUDE.md §2.6).
 */
export function reviewTally(item: EvidenceItem): ReviewTally | null {
  const review = item.review;
  if (!review) return null;

  const [only] = review.pending;
  const open =
    review.pending.length === 1 && only
      ? `${claimLabel(only.claim_type)}${
          review.journey_count > 1 ? ` (journey ${only.journey_index + 1})` : ""
        } still needed`
      : review.pending.length > 1
        ? `${review.pending.length} values still need review`
        : null;

  const decided = (
    [
      ["confirmed", review.confirmed],
      ["corrected", review.corrected],
      ["rejected", review.rejected],
    ] as const
  )
    .filter(([, count]) => count > 0)
    .map(([word, count]) => ({ word, count }));

  return { open, pendingCount: review.pending.length, decided };
}

/**
 * The original filename, or `null` when it only repeats the display name.
 *
 * An upload named after its file showed the same words twice, once with ".pdf". The
 * filename stays whenever it says something the name does not.
 */
export function distinctFilename(item: EvidenceItem): string | null {
  const filename = item.original_filename;
  if (!filename) return null;
  const stem = filename.replace(/\.[^.]+$/, "");
  return stem.toLowerCase() === item.display_name.toLowerCase() ? null : filename;
}

/**
 * The one-line note beneath a state, or null where the state speaks for itself.
 *
 * A failure always carries its reason. "No text found" carries one too, because without
 * it the user cannot tell whether their document is broken — it is not; a scan simply
 * has no text layer, and reading one needs OCR, which is M8.
 */
export function stateNote(item: EvidenceItem): string | null {
  if (item.failure_reason) return item.failure_reason;
  // Why analysis produced nothing, in the server's words. Checked before the generic
  // "no text found" below because the two are different findings with different
  // remedies: a scan has no text to read, whereas a spent daily budget means the text
  // was read fine and the analysis will work tomorrow. Telling someone with a perfectly
  // good document to try a different file is the failure this branch prevents.
  if (item.analysis_note) return item.analysis_note;
  if (item.processing_status === "PARTIALLY_COMPLETED") {
    // Read from the token rather than repeated here: the same sentence written twice in
    // two packages is two sentences that can drift.
    return evidenceProcessingTokens.partially_completed.meaning;
  }
  if (item.processing_status === "AWAITING_CONFIRMATION") {
    // Without this the announcement was "Values proposed. 1 page." — the page count
    // stripped of the column header that gives it meaning on screen, arriving straight
    // after a sentence about values, and parsing as *one page was proposed*. A number
    // announced with no context, on the one state the milestone exists to reach.
    return evidenceProcessingTokens.awaiting_confirmation.meaning;
  }
  return null;
}
