/**
 * The two-signal requirement status.
 *
 * A result has a **conclusion** (what we concluded) and a **currency** (whether that
 * conclusion is still current). They are orthogonal, and ADR-0001 is explicit that the UI
 * must render both and never collapse them: the canonical case is `SUPPORTED` + `STALE`,
 * which has to read as exactly that — supported, under inputs that have since changed.
 *
 * So this renders **two adjacent badges**, not one. There is deliberately no code path
 * that merges them, no "stale" variant of the conclusion badge, and no colour change to
 * the conclusion when it goes stale — the conclusion badge looks identical whether the
 * result is current or not, because the conclusion *is* identical.
 *
 * Three more rules the markup enforces:
 *
 * - **Never colour alone.** Every badge is glyph + text label. Remove all colour and the
 *   state is still readable.
 * - **A null currency renders no badge at all.** `NOT_YET_ASSESSED` has no currency, and
 *   showing "Current" there would claim the requirement had been assessed and found up to
 *   date. Absence of a badge is the honest rendering of absence of a result.
 * - **`CURRENT` also renders no badge.** It is the unremarkable case; adorning it would
 *   make "current" compete with the conclusion for attention and dilute the stale signal.
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";
import {
  conclusionStates,
  currencyStates,
  statusTokens,
  currencyTokens,
  type ConclusionState,
  type CurrencyState,
} from "./tokens";

/** Wire values are SCREAMING_SNAKE (`NOT_YET_ASSESSED`); token keys are lower_snake. */
export function toConclusionState(value: string): ConclusionState | null {
  const key = value.toLowerCase();
  return (conclusionStates as readonly string[]).includes(key) ? (key as ConclusionState) : null;
}

export function toCurrencyState(value: string | null | undefined): CurrencyState | null {
  if (!value) return null;
  const key = value.toLowerCase();
  return (currencyStates as readonly string[]).includes(key) ? (key as CurrencyState) : null;
}

export interface RequirementStatusProps {
  /** Conclusion as returned by the API, e.g. `"NEAR_THRESHOLD"`. */
  conclusion: string;
  /** Currency as returned by the API, or null when there is no result yet. */
  currency?: string | null;
  size?: "sm" | "md";
  className?: string;
}

export function RequirementStatus({
  conclusion,
  currency = null,
  size = "md",
  className,
}: RequirementStatusProps): JSX.Element {
  const conclusionState = toConclusionState(conclusion);
  const currencyState = toCurrencyState(currency);

  // An unrecognised conclusion is shown verbatim rather than guessed at or hidden: a
  // value this build does not know about must not be silently rendered as something safe.
  const token = conclusionState ? statusTokens[conclusionState] : null;
  const label = token ? token.label : conclusion;

  // CURRENT needs no adornment; a missing currency must not be invented as one.
  const showCurrency = currencyState !== null && currencyState !== "current";
  const currencyToken = showCurrency ? currencyTokens[currencyState] : null;

  const classes = ["cw-status-pair", size === "sm" ? "cw-status-pair--sm" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes}>
      <span
        className="cw-status-badge"
        data-conclusion={conclusionState ?? "unknown"}
        style={
          token
            ? {
                color: `var(${token.colorVar})`,
                background: `var(${token.surfaceVar})`,
              }
            : undefined
        }
      >
        {token ? <StatusGlyph name={token.glyph} size={size === "sm" ? 14 : 16} /> : null}
        <span>{label}</span>
      </span>

      {currencyToken ? (
        <span
          className="cw-status-badge cw-status-badge--currency"
          data-currency={currencyState}
          style={currencyToken.colorVar ? { color: `var(${currencyToken.colorVar})` } : undefined}
        >
          <StatusGlyph name={currencyToken.glyph} size={size === "sm" ? 14 : 16} />
          <span>{currencyToken.label}</span>
        </span>
      ) : null}
    </span>
  );
}
