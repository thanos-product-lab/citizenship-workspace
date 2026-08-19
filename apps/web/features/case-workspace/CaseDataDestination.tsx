"use client";

import type { components } from "@cw/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { JSX } from "react";

import { ResidencePanel } from "@/features/timeline/ResidencePanel";
import { caseKeys } from "@/lib/queries";

import { DeleteCaseControl } from "./DeleteCaseControl";

type Case = components["schemas"]["CaseResponse"];

/**
 * The Case data destination: the facts the system holds, and where they are corrected.
 *
 * This separates *what does my case mean* (Overview, Requirements) from *what does the
 * system know about me* (here). It is the editing surface — the proposed application
 * date, the travel history, and CSV import — and it is where the destructive action
 * lives, at the foot, away from the readiness journey.
 *
 * Note that editing anything here marks conclusions stale. That signal is rendered by the
 * case header, which is present on this destination too, so the user sees the consequence
 * of an edit on the page where they made it.
 */
export function CaseDataDestination({ caseId }: { caseId: string }): JSX.Element {
  const client = useQueryClient();

  return (
    <>
      <ResidencePanel caseId={caseId} />
      {/* Deletion returns the updated case, so write it straight into the cache rather
          than refetching: the server has already told us the new state. */}
      <DeleteCaseControl
        caseId={caseId}
        onDeleted={(updated: Case) => client.setQueryData(caseKeys.case(caseId), updated)}
      />
    </>
  );
}
