import type { Metadata } from "next";

import { CaseDataDestination } from "@/features/case-workspace/CaseDataDestination";

export const metadata: Metadata = { title: "Case data — Citizenship Workspace" };

// Next 15 delivers route params as a promise; unwrap before use.
export default async function CaseDataPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <CaseDataDestination caseId={caseId} />;
}
