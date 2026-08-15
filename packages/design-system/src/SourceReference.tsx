/**
 * The rule that produced a conclusion, and the guidance it cites.
 *
 * **The gap is stated, not filled.** MVP §8.8 requires every source link to display a
 * source version and a retrieval date. Neither is recorded until the `GuidanceVersion`
 * tables arrive with Migration 5 (ADR-0007). The nearest available substitutes — the
 * rule's own `effective_from`, or today's date — would both be fabricated provenance,
 * which is the single worst defect this product can ship. So when
 * `guidanceVersionRecorded` is false this component says so in plain words.
 *
 * It shows the **rule version the result actually ran under**, not the requirement's
 * currently-active rule. A historical result must display the rule that produced it, or
 * the explanation stops being reproducible (Domain §30.5).
 */

import type { JSX } from "react";

import { StatusGlyph } from "./StatusGlyph";

export interface GuidanceCitation {
  source: string;
  section?: string;
}

export interface SourceReferenceProps {
  semanticVersion: string;
  ruleSet: string;
  lifecycleStatus: string;
  effectiveFrom: string;
  guidance: GuidanceCitation[];
  guidanceVersionRecorded: boolean;
  /** Formats an ISO datetime for display; supplied by the app so formatting lives once. */
  formatDate: (iso: string) => string;
}

export function SourceReference({
  semanticVersion,
  ruleSet,
  lifecycleStatus,
  effectiveFrom,
  guidance,
  guidanceVersionRecorded,
  formatDate,
}: SourceReferenceProps): JSX.Element {
  return (
    <div className="cw-source">
      <dl className="cw-source__meta">
        <div>
          <dt>Rule version</dt>
          <dd className="cw-figure">{semanticVersion}</dd>
        </div>
        <div>
          <dt>Rule set</dt>
          <dd className="cw-figure">{ruleSet}</dd>
        </div>
        <div>
          <dt>In effect from</dt>
          <dd className="cw-figure">{formatDate(effectiveFrom)}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{lifecycleStatus.toLowerCase()}</dd>
        </div>
      </dl>

      {guidance.length > 0 ? (
        <ul className="cw-source__citations">
          {guidance.map((citation) => (
            <li key={`${citation.source}-${citation.section ?? ""}`}>
              <span className="cw-source__code cw-figure">{citation.source}</span>
              {citation.section ? <span>{citation.section}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="cw-stack__empty">No guidance source is cited for this rule.</p>
      )}

      {!guidanceVersionRecorded ? (
        <p className="cw-source__gap">
          <StatusGlyph name="slash" size={14} />
          <span>
            The version of this guidance and the date it was retrieved are not recorded
            yet, so they are not shown. The rule version above is exact.
          </span>
        </p>
      ) : null}
    </div>
  );
}
