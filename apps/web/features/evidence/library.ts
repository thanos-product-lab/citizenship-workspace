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

/** Sizes in the units a person uses, not bytes. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
