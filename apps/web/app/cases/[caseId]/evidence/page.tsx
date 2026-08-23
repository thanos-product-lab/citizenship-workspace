import type { Metadata } from "next";

import { EvidenceDestination } from "@/features/evidence/EvidenceDestination";

export const metadata: Metadata = { title: "Evidence · Citizenship workspace" };

export default async function EvidencePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <EvidenceDestination caseId={caseId} />;
}
