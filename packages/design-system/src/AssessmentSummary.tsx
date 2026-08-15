/**
 * The head of the requirement detail: what was concluded, and in one sentence why.
 *
 * The order is deliberate. The **conclusion and currency** come first as two badges, then
 * the headline figure, then the plain-language sentence. A reader who stops after the
 * badges has still been told the two things that matter most, and neither has been
 * softened by the sentence that follows.
 *
 * `summary` is always server-rendered from a summary code and its parameters
 * (`app/requirements/messages.py`). This component never composes a sentence of its own —
 * if the server has no template for a code, the text is absent and the structured fields
 * below carry the explanation instead.
 */

import type { JSX, ReactNode } from "react";

import { RequirementStatus } from "./RequirementStatus";

export interface AssessmentSummaryProps {
  title: string;
  description?: string | null;
  conclusion: string;
  currency?: string | null;
  /** The headline number and its threshold, e.g. "439 days against a threshold of 450". */
  figure?: ReactNode;
  /** Deterministic plain-language summary; null when the code has no template. */
  summary?: string | null;
  /** Rendered under the summary — the stale notice belongs here. */
  children?: ReactNode;
}

export function AssessmentSummary({
  title,
  description,
  conclusion,
  currency = null,
  figure,
  summary,
  children,
}: AssessmentSummaryProps): JSX.Element {
  return (
    <header className="cw-assessment">
      <div className="cw-assessment__head">
        <h1 className="cw-assessment__title">{title}</h1>
        <RequirementStatus conclusion={conclusion} currency={currency} />
      </div>

      {description ? <p className="cw-assessment__description">{description}</p> : null}
      {figure ? <p className="cw-assessment__figure cw-figure">{figure}</p> : null}
      {summary ? <p className="cw-assessment__summary">{summary}</p> : null}
      {children}
    </header>
  );
}
