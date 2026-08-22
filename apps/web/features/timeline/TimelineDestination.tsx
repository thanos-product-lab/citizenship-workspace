"use client";

import { useRef } from "react";

import { ResidenceTimeline } from "./ResidenceTimeline";

/**
 * The Timeline destination: your residence history, measured against your application
 * date.
 *
 * It shows *inputs*, not conclusions — no requirement conclusion or currency appears on
 * this screen. The conclusions drawn from these figures live on Requirements, and keeping
 * the two apart is what lets this one be computed live from the records as they stand
 * (ADR-0007). When the two disagree, the timeline says so rather than quietly agreeing.
 *
 * Renders no `<main>`: the case layout owns that landmark.
 */
export function TimelineDestination({ caseId }: { caseId: string }) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  return (
    <section aria-labelledby="timeline-heading">
      {/* "Residence timeline" here, "Timeline" in the navigation. The nav has a fixed
          width and unambiguous context; the page heading is what a screen-reader user
          hears on arrival and what a browser tab and a bookmark carry, so it says which
          timeline. */}
      <h2 id="timeline-heading" ref={headingRef} tabIndex={-1} className="cw-case-data__heading">
        Residence timeline
      </h2>
      <p className="cw-case-data__note">
        Every period you spent outside the UK, and how each one counts against the five-year
        period your case is measured over.
      </p>
      <ResidenceTimeline caseId={caseId} />
    </section>
  );
}
