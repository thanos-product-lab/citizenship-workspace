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

/**
 * Absent and unrecognised are **different answers** and must not share a branch.
 *
 * `null` means the requirement has no result, which is correctly rendered as no badge.
 * If an unrecognised value also returned `null`, a currency this build does not know —
 * a new enum member, a casing change, an API/client skew — would render exactly like
 * `CURRENT`: no badge, nothing remarkable. That is the most dangerous default available
 * here, so an unknown value is surfaced verbatim instead, mirroring the conclusion path.
 */
export type CurrencyResolution =
  | { kind: "absent" }
  | { kind: "known"; state: CurrencyState }
  | { kind: "unknown"; raw: string };

export function toCurrencyState(value: string | null | undefined): CurrencyResolution {
  if (!value) return { kind: "absent" };
  const key = value.toLowerCase();
  return (currencyStates as readonly string[]).includes(key)
    ? { kind: "known", state: key as CurrencyState }
    : { kind: "unknown", raw: value };
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
  const resolvedCurrency = toCurrencyState(currency);

  // An unrecognised conclusion is shown verbatim rather than guessed at or hidden: a
  // value this build does not know about must not be silently rendered as something safe.
  const token = conclusionState ? statusTokens[conclusionState] : null;
  const label = token ? token.label : conclusion;

  // CURRENT needs no adornment and an absent currency must not be invented as one — but
  // an unrecognised value gets a badge, so it can never pass for "current".
  const currencyBadge =
    resolvedCurrency.kind === "unknown"
      ? { label: resolvedCurrency.raw, colorVar: null, glyph: null, key: "unknown" }
      : resolvedCurrency.kind === "known" && resolvedCurrency.state !== "current"
        ? { ...currencyTokens[resolvedCurrency.state], key: resolvedCurrency.state }
        : null;

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

      {currencyBadge ? (
        <span
          className="cw-status-badge cw-status-badge--currency"
          data-currency={currencyBadge.key}
          style={currencyBadge.colorVar ? { color: `var(${currencyBadge.colorVar})` } : undefined}
        >
          {currencyBadge.glyph ? (
            <StatusGlyph name={currencyBadge.glyph} size={size === "sm" ? 14 : 16} />
          ) : null}
          <span>{currencyBadge.label}</span>
        </span>
      ) : null}
    </span>
  );
}
