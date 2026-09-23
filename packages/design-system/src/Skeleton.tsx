import type { CSSProperties, JSX } from "react";

/**
 * A placeholder shape where content is about to be.
 *
 * Always `aria-hidden`: a shape says nothing to a screen reader, so every use pairs it with
 * one status sentence ("Loading this case…") that does. The shimmer stops under
 * `prefers-reduced-motion`, where the block stays as a still grey shape.
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
