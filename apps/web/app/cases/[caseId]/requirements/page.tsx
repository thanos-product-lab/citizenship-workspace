import type { Metadata } from "next";

import { RequirementsDestination } from "@/features/requirements/RequirementsDestination";

// A distinct document title per destination (WCAG 2.4.2): these are full navigations, so
// the title is the first thing a screen-reader user hears on arrival and the only label
// in tab and history lists.
export const metadata: Metadata = { title: "Requirements — Citizenship Workspace" };

// Next 15 delivers route params as a promise; unwrap before use.
export default async function CaseRequirementsPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <RequirementsDestination caseId={caseId} />;
}
