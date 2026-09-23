import { Skeleton } from "@cw/design-system";
import type { JSX } from "react";

/**
 * What a case shows the moment a tab is clicked, while the next destination gets ready.
 *
 * Without this file the App Router keeps the old destination on screen until the new one
 * is ready, so a slow switch (a first visit compiling under `next dev`, or a slow network in
 * production) looked like a page that had stopped responding. Next renders this inside the
 * case layout, so the header and tabs stay where they are and only the content area changes.
 *
 * The shapes fade in after a short delay (`.cw-route-skeleton`), so a switch that lands in a
 * tenth of a second does not flash grey blocks; the sentence for screen readers is there at
 * once. The shapes are `aria-hidden`, as every skeleton here is.
 */
export default function CaseDestinationLoading(): JSX.Element {
  return (
    <>
      <p role="status" className="cw-visually-hidden">
        Loading…
      </p>
      <div className="cw-route-skeleton" aria-hidden="true" data-testid="destination-skeleton">
        <Skeleton width="10rem" height="1.5rem" />
        <Skeleton width="min(32rem, 90%)" height="0.875rem" />
        <Skeleton height="7rem" />
        <Skeleton height="7rem" />
      </div>
    </>
  );
}
