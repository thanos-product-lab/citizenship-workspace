/**
 * The explanation stack — the product's signature interaction.
 *
 * UI/UX §7.3 is explicit about what this is *not*: not a tooltip, not a disclosure widget,
 * and not an AI-generated paragraph. It is the domain model rendered:
 *
 *     Assessment
 *     ├── Facts used
 *     ├── Evidence used
 *     ├── Rule used
 *     ├── Limitations
 *     └── Next action
 *
 * So each layer is a real `<section>` with a real heading, and **the document outline is
 * the explanation structure**. A screen-reader user navigating by heading gets the same
 * tree a sighted user sees; nothing is hidden behind an interaction, because §15 forbids
 * putting critical information anywhere a user has to hover or expand to reach.
 *
 * A layer is always rendered, even when it has nothing in it. "No limitations were
 * recorded" and "no evidence is linked" are findings about the case, not absences to hide
 * — an explanation with layers silently missing invites the reader to assume they were
 * satisfied.
 */

import type { JSX, ReactNode } from "react";

export function ExplanationStack({ children }: { children: ReactNode }): JSX.Element {
  return <div className="cw-stack">{children}</div>;
}

export interface ExplanationLayerProps {
  /** The layer name, e.g. "Facts used". Rendered as a real heading. */
  title: string;
  /** Heading level. Defaults to 2: these sections are the top-level divisions of the
      detail page, matching how the case page structures its own sections. */
  headingLevel?: 2 | 3;
  /** Stable id so the heading can label the section. */
  id: string;
  /** One line framing what this layer answers. */
  note?: string | undefined;
  /** Shown instead of children when there is nothing in this layer. */
  emptyMessage?: string | undefined;
  children?: ReactNode;
}

export function ExplanationLayer({
  title,
  id,
  headingLevel = 2,
  note,
  emptyMessage,
  children,
}: ExplanationLayerProps): JSX.Element {
  const Heading = `h${headingLevel}` as "h2" | "h3";
  const isEmpty =
    children === undefined ||
    children === null ||
    children === false ||
    (Array.isArray(children) && children.length === 0);

  return (
    <section className="cw-stack__layer" aria-labelledby={id}>
      <Heading className="cw-stack__title" id={id}>
        {title}
      </Heading>
      {note ? <p className="cw-stack__note">{note}</p> : null}
      {isEmpty ? <p className="cw-stack__empty">{emptyMessage ?? "Nothing recorded."}</p> : children}
    </section>
  );
}
