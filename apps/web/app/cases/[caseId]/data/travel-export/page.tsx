import type { Metadata } from "next";

import { TravelExport } from "@/features/timeline/TravelExport";

export const metadata: Metadata = { title: "Travel list · Citizenship Workspace" };

// Next 15 delivers route params as a promise; unwrap before use.
export default async function TravelExportPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <TravelExport caseId={caseId} />;
}
