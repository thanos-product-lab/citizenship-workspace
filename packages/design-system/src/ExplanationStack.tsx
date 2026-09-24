/**
 * The explanation stack — the product's signature interaction.
 *
 * UI/UX §7.3 is explicit about what this is *not*: not a tooltip, not a disclosure widget,
 * and not an AI-generated paragraph. It is the domain model rendered:
 *
 *     Assessment
 *     ├── Limitations
 *     ├── Next action
 *     ├── Facts used
 *     ├── Evidence used
 *     └── Rule used
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
 *
 * **Compact when empty, never removed**. An empty layer keeps its heading and
 * its finding, and drops the framing note, which introduces content that is not there.
 * `data-empty` lets the stylesheet set the two on one line and close the space between
 * consecutive empty layers, so a mostly-empty explanation no longer takes a screen of
 * headings to say "nothing here".
 */

import type { JSX, ReactNode } from "react";

export function ExplanationStack({ children }: { children: ReactNode }): JSX.Element {
  return <div className="cw-stack">{children}</div>;
}

export interface ExplanationLayerProps {
  /** The layer name, e.g. "Facts used". Rendered as a real heading. */
  title: string;
  /** Heading level. Defaults to 3: the requirement title above these is an `h2`, because
      the case title in the persistent header is the page's `h1`. The layers are divisions
      *of the requirement*, so nesting one deeper is what the outline actually describes.
      They were `h2` while the requirement title was a second `h1` on the page. */
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
  headingLevel = 3,
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
    <section
      className="cw-stack__layer"
      aria-labelledby={id}
      data-empty={isEmpty ? "true" : undefined}
    >
      <Heading className="cw-stack__title" id={id}>
        {title}
      </Heading>
      {note && !isEmpty ? <p className="cw-stack__note">{note}</p> : null}
      {isEmpty ? <p className="cw-stack__empty">{emptyMessage ?? "Nothing recorded."}</p> : children}
    </section>
  );
}
