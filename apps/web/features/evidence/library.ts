import type { components } from "@cw/api-client";

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
