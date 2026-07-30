"use client";

import { ApplicationDateCard } from "./ApplicationDateCard";
import { TravelHistory } from "./TravelHistory";

/**
 * The residence-input section of an active case: the proposed application date and the
 * travel history. M3A input layer only — no qualifying-period, absence, or presence
 * calculation is shown; those deterministic results arrive in the next milestone.
 */
export function ResidencePanel({ caseId }: { caseId: string }) {
  return (
    <section aria-labelledby="residence-heading" style={{ marginTop: "var(--cw-space-8)" }}>
      <h2 id="residence-heading" style={{ margin: 0, fontSize: "var(--cw-text-xl)" }}>
        Residence
      </h2>
      <ApplicationDateCard caseId={caseId} />
      <TravelHistory caseId={caseId} />
    </section>
  );
}
