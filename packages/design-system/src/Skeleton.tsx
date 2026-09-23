import type { CSSProperties, JSX } from "react";

/**
 * A placeholder shape where content is about to be.
 *
 * Always `aria-hidden`: a shape says nothing to a screen reader, so every use pairs it with
 * one status sentence ("Loading this case…") that does. The shimmer stops under
 * `prefers-reduced-motion`, where the block stays as a still grey shape.
 *
 * **Render it as soon as the thing it stands for is loading.** It holds itself back: the
 * stylesheet keeps it invisible for 150ms and then fades it in, so a fast load shows
 * nothing. That delay lives in CSS so it works in the server's HTML, before any JavaScript
 * has arrived; a JavaScript timer left slow connections with an empty space instead.
 */
export function Skeleton({
  width = "100%",
  height = "1rem",
  round = false,
  style,
}: {
  width?: CSSProperties["width"];
  height?: CSSProperties["height"];
  /** A circle, for an avatar. */
  round?: boolean;
  style?: CSSProperties;
}): JSX.Element {
  return (
    <span
      aria-hidden="true"
      className="cw-skeleton"
      data-round={round ? "true" : undefined}
      style={{ width, height, ...style }}
    />
  );
}
