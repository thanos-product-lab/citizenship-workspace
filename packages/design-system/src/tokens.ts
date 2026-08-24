/**
 * Semantic token maps.
 *
 * Raw values live in tokens.css as CSS custom properties. This module maps
 * domain states to those variables **plus a non-colour glyph and a label** —
 * because colour must never be the only signal (CLAUDE.md §6, WCAG 2.2). Glyph
 * names are stable identifiers resolved to real icons by the components in M4.
 */

/**
 * The non-colour indicators. Every token below names one of these, and `StatusGlyph`
 * resolves each to a shape — so a token naming a glyph the icon set does not draw is a
 * compile error rather than a silently missing signal.
 */
export const glyphNames = [
  // conclusions
  "check",
  "dashed-circle",
  "conflict",
  "gauge",
  "scale",
  "shield",
  "minus-circle",
  "dash",
  // currency
  "dot",
  "clock",
  "history",
  "preview",
  // provenance
  "proposed",
  "pencil",
  "equals",
  "paperclip",
  "slash",
] as const;

export type GlyphName = (typeof glyphNames)[number];

// --- Requirement conclusion (DOMAIN_MODEL_RFC §30.2) ---

export const conclusionStates = [
  "supported",
  "incomplete",
  "inconsistent",
  "near_threshold",
  "requires_judgement",
  "professional_review_recommended",
  "not_currently_satisfied",
  "not_yet_assessed",
] as const;

export type ConclusionState = (typeof conclusionStates)[number];

export interface StatusToken {
  /** CSS custom property for the colour (text/icon), AA-verified on its surface. */
  readonly colorVar: string;
  /** CSS custom property for the soft badge surface. */
  readonly surfaceVar: string;
  /** Non-colour indicator — colour is never the only signal. */
  readonly glyph: GlyphName;
  /** Short human label. */
  readonly label: string;
}

export const statusTokens: Record<ConclusionState, StatusToken> = {
  supported: {
    colorVar: "--cw-status-supported",
    surfaceVar: "--cw-status-supported-surface",
    glyph: "check",
    label: "Supported",
  },
  incomplete: {
    colorVar: "--cw-status-incomplete",
    surfaceVar: "--cw-status-incomplete-surface",
    glyph: "dashed-circle",
    label: "Incomplete",
  },
  inconsistent: {
    colorVar: "--cw-status-inconsistent",
    surfaceVar: "--cw-status-inconsistent-surface",
    glyph: "conflict",
    label: "Inconsistent",
  },
  near_threshold: {
    colorVar: "--cw-status-near-threshold",
    surfaceVar: "--cw-status-near-threshold-surface",
    glyph: "gauge",
    label: "Near threshold",
  },
  requires_judgement: {
    colorVar: "--cw-status-requires-judgement",
    surfaceVar: "--cw-status-requires-judgement-surface",
    glyph: "scale",
    label: "Requires judgement",
  },
  professional_review_recommended: {
    colorVar: "--cw-status-professional-review",
    surfaceVar: "--cw-status-professional-review-surface",
    glyph: "shield",
    label: "Professional review recommended",
  },
  not_currently_satisfied: {
    colorVar: "--cw-status-not-satisfied",
    surfaceVar: "--cw-status-not-satisfied-surface",
    glyph: "minus-circle",
    label: "Not currently satisfied",
  },
  not_yet_assessed: {
    colorVar: "--cw-status-not-assessed",
    surfaceVar: "--cw-status-not-assessed-surface",
    glyph: "dash",
    label: "Not yet assessed",
  },
};

// --- Currency (orthogonal to conclusion; CLAUDE.md §2.4) ---

export const currencyStates = ["current", "stale", "superseded", "provisional"] as const;

export type CurrencyState = (typeof currencyStates)[number];

export interface CurrencyToken {
  /** null for `current`, which needs no adornment. */
  readonly colorVar: string | null;
  readonly glyph: GlyphName;
  readonly label: string;
}

export const currencyTokens: Record<CurrencyState, CurrencyToken> = {
  current: { colorVar: null, glyph: "dot", label: "Current" },
  stale: { colorVar: "--cw-currency-stale", glyph: "clock", label: "Stale" },
  superseded: { colorVar: "--cw-currency-superseded", glyph: "history", label: "Superseded" },
  // Labelled "Preview", not "Provisional". The domain uses "provisional" for two unrelated
  // things: the currency of an unsaved simulation (Domain §42.2) and, in RULES_SPEC §6.2,
  // a total computed *including unconfirmed travel records*. Both now appear in one
  // simulation response — `after.currency: "PROVISIONAL"` beside
  // `summary_parameters.provisional_days` — so user-facing copy uses "preview" for the
  // first and "unconfirmed records" for the second, and the word "provisional" for
  // neither. The enum value, the CSS custom property and the glyph are unchanged; only
  // what a human reads.
  provisional: { colorVar: "--cw-currency-provisional", glyph: "preview", label: "Preview" },
};

// --- Provenance (how a value came to be; UI/UX §3.4, §18.5) ---

export const provenanceKinds = [
  "ai_proposed",
  "user_confirmed",
  "user_corrected",
  "system_calculated",
  "evidence_supported",
  "conflicting",
  "stale",
  "unavailable",
] as const;

export type ProvenanceKind = (typeof provenanceKinds)[number];

export interface ProvenanceToken {
  readonly colorVar: string;
  readonly glyph: GlyphName;
  readonly label: string;
}

export const provenanceTokens: Record<ProvenanceKind, ProvenanceToken> = {
  ai_proposed: { colorVar: "--cw-provenance-ai-proposed", glyph: "proposed", label: "AI proposed" },
  user_confirmed: { colorVar: "--cw-provenance-user-confirmed", glyph: "check", label: "Confirmed" },
  user_corrected: { colorVar: "--cw-provenance-user-corrected", glyph: "pencil", label: "Corrected" },
  system_calculated: {
    colorVar: "--cw-provenance-system-calculated",
    glyph: "equals",
    label: "Calculated",
  },
  evidence_supported: {
    colorVar: "--cw-provenance-evidence-supported",
    glyph: "paperclip",
    label: "Evidence",
  },
  conflicting: { colorVar: "--cw-provenance-conflicting", glyph: "conflict", label: "Conflicting" },
  stale: { colorVar: "--cw-provenance-stale", glyph: "clock", label: "Stale" },
  unavailable: { colorVar: "--cw-provenance-unavailable", glyph: "slash", label: "Unavailable" },
};

// --- Evidence processing state (DOMAIN_MODEL_RFC §14.4) ---

/**
 * The processing states this build can actually render, and only those.
 *
 * §14.4 defines nine. This map holds the ones a document can *reach* in the milestone
 * that ships it, and grows as producers land:
 *
 * - `uploaded` — M7 slice 1.
 * - `validating`, `unsupported`, `failed` — M7 slice 2, with validation in the worker.
 * - `extracting_text`, `analysing`, `completed`, `partially_completed` — M7 slice 3,
 *   with deterministic extraction.
 * - `awaiting_confirmation` — **M8, and deliberately absent**. It has no producer until
 *   extracted claims exist. A token for it would let the UI name it as a stage a
 *   document might enter, which is a promise the product cannot keep; a state the
 *   product names but cannot reach is worse than one it does not mention.
 *   `EvidenceState` renders any state it has no token for verbatim, so when M8 makes it
 *   reachable the wire value shows up honestly rather than silently as something benign.
 */
export const evidenceProcessingStates = [
  "uploaded",
  "validating",
  "unsupported",
  "failed",
] as const;

export type EvidenceProcessingState = (typeof evidenceProcessingStates)[number];

export interface EvidenceProcessingToken {
  readonly colorVar: string;
  readonly glyph: GlyphName;
  readonly label: string;
  /** What the state means, for the caption a badge alone cannot carry. */
  readonly meaning: string;
}

export const evidenceProcessingTokens: Record<
  EvidenceProcessingState,
  EvidenceProcessingToken
> = {
  uploaded: {
    colorVar: "--cw-provenance-evidence-supported",
    glyph: "paperclip",
    label: "Uploaded",
    // True both before validation runs and after it passes. In this milestone nothing
    // reads a document's contents, so "stored and checked" and "stored" say the same
    // thing to a user — and claiming more would be the false reassurance the product
    // exists to avoid.
    meaning: "Stored, and not yet read by anything.",
  },
  validating: {
    colorVar: "--cw-currency-provisional",
    glyph: "clock",
    label: "Validating",
    meaning: "Checking the file is the kind of document it says it is.",
  },
  unsupported: {
    colorVar: "--cw-status-incomplete",
    glyph: "minus-circle",
    label: "Unsupported",
    meaning: "This file is not a document the product can read.",
  },
  failed: {
    colorVar: "--cw-status-not-satisfied",
    glyph: "conflict",
    label: "Failed",
    meaning: "Something went wrong reading this file. You can try again.",
  },
};
