/**
 * What has happened to an uploaded document, in the product's own vocabulary.
 *
 * Two rules, both about not saying more than is true:
 *
 * - **Domain states only, never queue states.** The API types this field to Domain
 *   §14.4, so a Celery state cannot arrive here through the schema. This component is
 *   the second half of that guarantee: it renders what it is given, and a value it has
 *   no token for is shown **verbatim** rather than mapped to something benign. An
 *   unrecognised state that rendered as "Uploaded" would be the dangerous default —
 *   the same reasoning as `RequirementStatus.toCurrencyState`.
 * - **No progress affordance.** There is no stepper, no "next: …", no ordered track of
 *   stages. A document's route through §14.4 is not a fixed pipeline — it can end at
 *   `UNSUPPORTED` after validation or at `PARTIALLY_COMPLETED` after extraction — and
 *   `AWAITING_CONFIRMATION` has no producer at all until M8. Drawing the stages as a
 *   path would name destinations this build cannot reach.
 *
 * Colour is never the only signal: every state is glyph + text label, and the component
 * is legible with colour removed.
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";
import {
  evidenceProcessingStates,
  evidenceProcessingTokens,
  type EvidenceProcessingState,
} from "./tokens";

/** Wire values are SCREAMING_SNAKE (`EXTRACTING_TEXT`); token keys are lower_snake. */
export function toEvidenceProcessingState(value: string): EvidenceProcessingState | null {
  const key = value.toLowerCase();
  return (evidenceProcessingStates as readonly string[]).includes(key)
    ? (key as EvidenceProcessingState)
    : null;
}

export interface EvidenceStateProps {
  /** Processing status as returned by the API, e.g. `"UPLOADED"`. */
  status: string;
  /** Render the one-line meaning beneath the badge. */
  withMeaning?: boolean;
  size?: "sm" | "md";
  className?: string;
}

export function EvidenceState({
  status,
  withMeaning = false,
  size = "md",
  className,
}: EvidenceStateProps): JSX.Element {
  const state = toEvidenceProcessingState(status);
  const token = state ? evidenceProcessingTokens[state] : null;

  const classes = ["cw-evidence-state", size === "sm" ? "cw-evidence-state--sm" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes}>
      <span
        className="cw-status-badge"
        data-evidence-state={state ?? "unknown"}
        style={token ? { color: `var(${token.colorVar})` } : undefined}
      >
        {token ? <StatusGlyph name={token.glyph} size={size === "sm" ? 14 : 16} /> : null}
        <span>{token ? token.label : status}</span>
      </span>
      {withMeaning && token ? (
        <span className="cw-evidence-state__meaning">{token.meaning}</span>
      ) : null}
    </span>
  );
}
