import { OverviewDestination } from "@/features/overview/OverviewDestination";

// Next 15 delivers route params as a promise; unwrap before use.
export default async function CaseOverviewPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}) {
  const { caseId } = await params;
  return <OverviewDestination caseId={caseId} />;
}
