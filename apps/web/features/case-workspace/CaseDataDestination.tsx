"use client";

import type { components } from "@cw/api-client";
import { useQueryClient } from "@tanstack/react-query";
import type { JSX } from "react";

import { ApplicationDateCard } from "@/features/timeline/ApplicationDateCard";
import { TravelHistory } from "@/features/timeline/TravelHistory";
import { caseKeys } from "@/lib/queries";

import { DeleteCaseControl } from "./DeleteCaseControl";

type Case = components["schemas"]["CaseResponse"];

/**
 * The Case data destination: the facts the system holds, and where they are corrected.
 *
 * This separates *what does my case mean* (Overview, Requirements) from *what does the
 * system know about me* (here). It is the editing surface — the proposed application date
 * and the travel history, including CSV import — and it is where the destructive action
 * lives, at the foot, away from the readiness journey.
 *
 * The heading says **Case data**, not "Residence". That label was correct while this was
 * the residence *section* of a single scrolling page; once it became the destination it
 * described the whole page as being about residence, with the delete control sitting
 * outside it as a sibling. The intermediate `ResidencePanel` went with it rather than
 * being renamed — under this information architecture it was a wrapper around two
 * unrelated cards with nothing left to hold them together.
 *
 * The note under the heading is not decoration: editing anything here marks conclusions
 * stale, and saying so before the controls is what makes the case header's stale notice
 * legible as a consequence rather than a surprise.
 */
export function CaseDataDestination({ caseId }: { caseId: string }): JSX.Element {
  const client = useQueryClient();

  return (
    <>
      <section className="cw-case-data" aria-labelledby="case-data-heading">
        <h2 id="case-data-heading" className="cw-case-data__heading">
          Case data
        </h2>
        <p className="cw-case-data__note">
          The facts your case is assessed against. Changing any of them marks the
          conclusions drawn from it stale until you recalculate.
        </p>

        <ApplicationDateCard caseId={caseId} />
        <TravelHistory caseId={caseId} />
      </section>

      {/* Deletion returns the updated case, so write it straight into the cache rather
          than refetching: the server has already told us the new state. */}
      <DeleteCaseControl
        caseId={caseId}
        onDeleted={(updated: Case) => client.setQueryData(caseKeys.case(caseId), updated)}
      />
    </>
  );
}
