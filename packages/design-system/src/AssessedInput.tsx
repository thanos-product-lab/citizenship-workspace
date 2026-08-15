/**
 * One input a rule read, and the badge describing how its value came to be.
 *
 * Two markers here are load-bearing, and both exist to stop a list of rows reading as
 * more than it is:
 *
 * - **`countsAsConfirmed === false`** says this record did *not* contribute to the
 *   confirmed figure (the §6.1 trust gate). Twelve travel rows look like twelve pieces of
 *   corroboration; without this marker the reader has no way to know some of them counted
 *   for nothing. Volume must never read as evidence.
 * - **`isStillCurrent === false`** says this exact version has been edited since the
 *   result was produced. It is what turns "this result is stale" into "your Italy trip
 *   changed", and it is why the row keeps showing the value the rule *read* rather than
 *   the value the record holds now.
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";
import { provenanceTokens, type ProvenanceKind } from "./tokens";

export function ProvenanceBadge({ kind }: { kind: string }): JSX.Element {
  const key = kind.toLowerCase() as ProvenanceKind;
  const token = provenanceTokens[key];
  // An unrecognised provenance kind is shown verbatim rather than guessed at, for the
  // same reason an unrecognised conclusion is: silently picking a benign-looking token
  // would be the UI asserting something the domain did not say.
  if (!token) {
    return (
      <span className="cw-provenance" data-provenance="unknown">
        {kind}
      </span>
    );
  }
  return (
    <span
      className="cw-provenance"
      data-provenance={key}
      style={{ color: `var(${token.colorVar})` }}
    >
      <StatusGlyph name={token.glyph} size={14} />
      <span>{token.label}</span>
    </span>
  );
}

export interface AssessedInputProps {
  label: string;
  value: string;
  detail?: string | null;
  provenanceKind: string;
  /** Null where the trust gate does not apply (the application date, profile answers). */
  countsAsConfirmed?: boolean | null;
  isStillCurrent: boolean;
  /** The record was deleted after this result was produced. Distinct from an edit: a
      tombstone keeps the record pointing at this version, so removal is invisible to
      `isStillCurrent` and needs its own signal. */
  isRemoved?: boolean;
  unavailable?: boolean;
}

export function AssessedInput({
  label,
  value,
  detail,
  provenanceKind,
  countsAsConfirmed = null,
  isStillCurrent,
  isRemoved = false,
  unavailable = false,
}: AssessedInputProps): JSX.Element {
  return (
    <li className="cw-input" data-unavailable={unavailable ? "true" : undefined}>
      <div className="cw-input__head">
        <span className="cw-input__label">{label}</span>
        <ProvenanceBadge kind={provenanceKind} />
      </div>

      <p className="cw-input__value cw-figure">{value}</p>
      {detail ? <p className="cw-input__detail">{detail}</p> : null}

      {countsAsConfirmed === false ? (
        <p className="cw-input__flag" data-flag="not-counted">
          <StatusGlyph name="slash" size={14} />
          <span>Did not count towards the confirmed figure.</span>
        </p>
      ) : null}

      {isRemoved ? (
        <p className="cw-input__flag" data-flag="moved">
          <StatusGlyph name="slash" size={14} />
          <span>
            This record has been removed since. The value above is what the rule read.
          </span>
        </p>
      ) : !isStillCurrent && !unavailable ? (
        <p className="cw-input__flag" data-flag="moved">
          <StatusGlyph name="clock" size={14} />
          <span>This has been edited since. The value above is what the rule read.</span>
        </p>
      ) : null}
    </li>
  );
}
