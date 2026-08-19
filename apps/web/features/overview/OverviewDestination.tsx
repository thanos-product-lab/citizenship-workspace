"use client";

import type { JSX } from "react";

import { useCaseOverview } from "@/features/case-workspace/useCaseOverview";

import { CaseOverviewPanel } from "./CaseOverviewPanel";

/**
 * The Overview destination: where the case stands, and the few things worth doing next.
 *
 * It deliberately holds only the summary. The requirements themselves live under
 * Requirements and the editable inputs under Case data, so this page can answer its three
 * questions — what is the state of my case, what needs my attention, what should I do
 * next — without the reader scrolling past a travel table to reach them.
 */
export function OverviewDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data: overview, status } = useCaseOverview(caseId);

  if (status === "pending") {
    // Reserve the space so the panel does not shove later content down the page when the
    // fetch resolves.
    return <div className="cw-overview__placeholder" aria-hidden="true" />;
  }

  if (status === "error" || !overview) {
    // The counts survive on the Requirements destination, so those are recoverable. Two
    // things do not appear anywhere else and the user must not read their absence as
    // "nothing to report": the priority actions, and the case-level stale signal.
    return (
      <p className="cw-overview__unavailable">
        This summary couldn’t be loaded, so any outstanding actions aren’t shown. Open
        Requirements to see the current conclusions.
      </p>
    );
  }

  return <CaseOverviewPanel overview={overview} />;
}
