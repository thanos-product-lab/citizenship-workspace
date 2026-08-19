"use client";

import type { JSX } from "react";

import { useCaseOverview } from "@/features/case-workspace/useCaseOverview";

import { RequirementsList } from "./RequirementsList";

/**
 * The Requirements destination: the full assessment model for the case.
 *
 * The per-group summaries come from the overview projection rather than being recomputed
 * here — a group's currency inherits its weakest member (ADR-0010), and deriving that
 * twice in two places is how the two would eventually disagree. Both readers share one
 * query key, so this costs no extra request.
 */
export function RequirementsDestination({ caseId }: { caseId: string }): JSX.Element {
  const { data: overview } = useCaseOverview(caseId);

  return <RequirementsList caseId={caseId} groupSummaries={overview?.groups ?? []} />;
}
