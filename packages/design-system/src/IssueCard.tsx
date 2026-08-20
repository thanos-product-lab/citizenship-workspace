/**
 * One item in the issue queue.
 *
 * The register is the point, and UI/UX §10 sets it: this experience should feel
 * *manageable rather than alarming*. So there is no red banner, no exclamation, no
 * "Something went wrong" — an issue is a thing to do, not an emergency, and a queue that
 * shouts trains the reader to stop looking at it.
 *
 * Three rules the markup enforces rather than merely encourages:
 *
 * - **Severity is never colour alone.** It is a glyph, a word, and a border weight. The
 *   card renders identically legible in greyscale.
 * - **The impact line says what follows, never what will happen.** "This conclusion may
 *   no longer match your case data", not "your application may be refused". This product
 *   does not predict outcomes (CLAUDE.md §1).
 * - **A recurrence says so.** An issue that was raised, resolved and has come back is
 *   marked, because presenting a second occurrence as a first hides the fact that a fix
 *   did not hold.
 *
 * All prose arrives rendered from the server (`title`, `body`, `impact`). Nothing here
 * composes a sentence, so the copy rules in `messages.py` hold in one place.
 */

import type { JSX, ReactNode } from "react";

import { StatusGlyph } from "./StatusGlyph";
import type { GlyphName } from "./tokens";

export type IssueSeverity =
  | "BLOCKING"
  | "ACTION_REQUIRED"
  | "REVIEW_REQUIRED"
  | "INFORMATION";

interface SeverityToken {
  label: string;
  glyph: GlyphName;
}

/** Severity → the word and glyph carrying it. Colour is applied from these in CSS, never
 *  instead of them. */
export const issueSeverityTokens: Record<IssueSeverity, SeverityToken> = {
  BLOCKING: { label: "Blocks preparation", glyph: "minus-circle" },
  ACTION_REQUIRED: { label: "Needs an action", glyph: "gauge" },
  REVIEW_REQUIRED: { label: "Worth reviewing", glyph: "scale" },
  INFORMATION: { label: "For information", glyph: "dot" },
};

export interface IssueCardProps {
  title: string;
  severity: IssueSeverity;
  /** What is wrong, rendered by the server. */
  body?: string | null | undefined;
  /** Why it matters — the consequence, never a prediction. */
  impact?: string | null | undefined;
  /** True when this cause was raised before, resolved, and has returned. */
  hasRecurred?: boolean | undefined;
  /** Actions the user can take. Rendered in a group so the card has one action row. */
  actions?: ReactNode | undefined;
  /** A link back to whatever the issue is about. */
  affectedLink?: ReactNode | undefined;
  /**
   * The card title's heading level. Defaults to 3 so the component is usable on its own,
   * but a card nested under a group heading must go one deeper — otherwise the title is a
   * *sibling* of the heading that contains it, and heading navigation flattens the
   * grouping this queue is organised by.
   */
  headingLevel?: 2 | 3 | 4 | 5 | undefined;
  /** Id for the title, so the card's `<article>` can be named by it. */
  titleId?: string | undefined;
}

export function IssueCard({
  title,
  severity,
  body,
  impact,
  hasRecurred = false,
  actions,
  affectedLink,
  headingLevel = 3,
  titleId,
}: IssueCardProps): JSX.Element {
  const token = issueSeverityTokens[severity] ?? issueSeverityTokens.REVIEW_REQUIRED;
  const Heading = `h${headingLevel}` as const;

  return (
    // Named by its own title: an <article> is exposed to assistive technology as a
    // landmark-like region, and an unnamed one announces as "article" and nothing else.
    <article className="cw-issue-card" data-severity={severity} aria-labelledby={titleId}>
      <div className="cw-issue-card__head">
        <Heading className="cw-issue-card__title" id={titleId}>
          {title}
        </Heading>
        <span className="cw-issue-card__severity">
          <StatusGlyph name={token.glyph} size={14} />
          {token.label}
        </span>
      </div>

      {body ? <p className="cw-issue-card__body">{body}</p> : null}

      {impact ? (
        <p className="cw-issue-card__impact">
          {/* Labelled rather than implied: without it this reads as a second description
              sentence, and the reason it is here is that it answers a different question. */}
          <span className="cw-issue-card__impact-label">Why this matters</span>
          {impact}
        </p>
      ) : null}

      {hasRecurred ? (
        <p className="cw-issue-card__recurrence">
          <StatusGlyph name="history" size={14} />
          <span>This was resolved before and has come back.</span>
        </p>
      ) : null}

      {affectedLink || actions ? (
        <div className="cw-issue-card__foot">
          {affectedLink ? <span className="cw-issue-card__affected">{affectedLink}</span> : null}
          {actions ? <span className="cw-issue-card__actions">{actions}</span> : null}
        </div>
      ) : null}
    </article>
  );
}
