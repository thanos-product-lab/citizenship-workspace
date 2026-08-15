/**
 * The notice that sits beside a stale conclusion.
 *
 * The wording is the whole point. A stale result means the inputs beneath a conclusion
 * changed and it has **not been re-evaluated** — so this must never say the conclusion
 * "still stands", "still holds", or "is still valid". Saying so would collapse currency
 * into conclusion in prose while the badges keep them apart (ADR-0001), which is harder
 * to spot and just as damaging.
 *
 * What it may say is that the conclusion is *preserved*: this is what was concluded
 * before the change, and it has not been rechecked.
 *
 * Three signals, so it survives greyscale: an amber rule, a clock glyph, and the word.
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";

export interface StaleAssessmentNoticeProps {
  /** Deterministic server-rendered reason, e.g. "Your travel records changed…". */
  reason?: string | null;
  /** Optional extra line, e.g. naming the input that moved. */
  detail?: string | null;
}

export function StaleAssessmentNotice({
  reason,
  detail,
}: StaleAssessmentNoticeProps): JSX.Element {
  return (
    <p className="cw-stale-notice">
      <StatusGlyph name="clock" size={16} />
      <span>
        {reason ?? "An input changed after this was worked out."} This is the conclusion from
        before that change; it has not been rechecked.
        {detail ? ` ${detail}` : ""}
      </span>
    </p>
  );
}
