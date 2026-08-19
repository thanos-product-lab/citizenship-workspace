"use client";

import { cloneElement, isValidElement } from "react";
import type { ReactElement, ReactNode } from "react";

/**
 * Shared field/style primitives for the residence-input surfaces, matching the
 * conventions established in RouteOnboarding: token-driven inline styles, and a
 * `Field` that owns the label↔control and hint/error↔control associations so every
 * error is bound to its field and announced (accessibility gate).
 */

export const inputStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-3)",
  border: "1px solid var(--cw-border)",
  borderRadius: "var(--cw-radius-md)",
  background: "var(--cw-surface)",
  color: "inherit",
  maxWidth: "24rem",
};

export const buttonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-accent)",
  color: "var(--cw-accent-contrast)",
  border: "none",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
  textDecoration: "none",
};

export const secondaryButtonStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-4)",
  background: "var(--cw-surface)",
  color: "inherit",
  border: "1px solid var(--cw-border-strong)",
  borderRadius: "var(--cw-radius-md)",
  fontWeight: "var(--cw-weight-medium)",
  cursor: "pointer",
};

export const dangerButtonStyle: React.CSSProperties = {
  ...buttonStyle,
  background: "var(--cw-status-not-satisfied)",
};

export const linkButtonStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  padding: 0,
  color: "inherit",
  textDecoration: "underline",
  cursor: "pointer",
  font: "inherit",
};

export const cardStyle: React.CSSProperties = {
  marginTop: "var(--cw-space-6)",
  padding: "var(--cw-space-5)",
  background: "var(--cw-surface)",
  border: "1px solid var(--cw-border)",
  borderRadius: "var(--cw-radius-md)",
};

export const errorTextStyle: React.CSSProperties = { color: "var(--cw-status-not-satisfied)" };

// The travel table's cell styles moved to `components.css` as `.cw-trips`: they have to
// reflow below 34rem, and a media query is one of the things inline styles cannot express.

/**
 * A status pill: soft tinted surface, matching-hue text, a hairline border, and a
 * decorative leading glyph. Colour is reinforcement only — the label carries the
 * meaning (non-colour-status gate). Mirrors the design-system `statusTokens` shape.
 */
export function StatusBadge({
  colorVar,
  surfaceVar,
  glyph,
  label,
}: {
  colorVar: string;
  surfaceVar: string;
  glyph: string;
  label: string;
}) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--cw-space-1)",
        padding: "2px var(--cw-space-2)",
        borderRadius: "var(--cw-radius-sm)",
        background: `var(${surfaceVar})`,
        color: `var(${colorVar})`,
        border: `1px solid color-mix(in oklab, var(${colorVar}) 32%, var(--cw-surface))`,
        fontSize: "var(--cw-text-xs)",
        fontWeight: "var(--cw-weight-semibold)",
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden="true" style={{ fontSize: "0.9em" }}>
        {glyph}
      </span>
      {label}
    </span>
  );
}

/**
 * Label + optional hint + optional error + control. Stamps `aria-describedby` onto
 * the single child control (hint first, then error) so both are announced, and sets
 * `aria-invalid` when an error is present. A control with neither carries no dangling
 * reference.
 */
export function Field({
  id,
  label,
  hint,
  error,
  errorIsLive = true,
  children,
}: {
  id: string;
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  // When the caller moves focus to this field on error, set false: the control
  // announces its described-by error on focus, so role="alert" would double-speak.
  errorIsLive?: boolean | undefined;
  children: ReactNode;
}) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  let control: ReactNode = children;
  if (isValidElement(children) && (describedBy || error)) {
    // Build the injected props conditionally: passing an explicit `undefined` would
    // violate exactOptionalPropertyTypes on the control's aria attributes.
    const extra: { "aria-describedby"?: string; "aria-invalid"?: true } = {};
    if (describedBy) extra["aria-describedby"] = describedBy;
    if (error) extra["aria-invalid"] = true;
    control = cloneElement(
      children as ReactElement<{ "aria-describedby"?: string; "aria-invalid"?: true }>,
      extra,
    );
  }
  return (
    <div style={{ display: "grid", gap: "var(--cw-space-2)" }}>
      <label htmlFor={id} style={{ fontWeight: "var(--cw-weight-medium)" }}>
        {label}
      </label>
      {hint && (
        <p id={hintId} style={{ margin: 0, fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)" }}>
          {hint}
        </p>
      )}
      {error && (
        <p
          id={errorId}
          role={errorIsLive ? "alert" : undefined}
          style={{ margin: 0, fontSize: "var(--cw-text-sm)", ...errorTextStyle }}
        >
          {error}
        </p>
      )}
      {control}
    </div>
  );
}
