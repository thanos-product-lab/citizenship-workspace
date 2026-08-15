import { RequirementDetail } from "@/features/requirements/RequirementDetail";

// Next 15 delivers route params as a promise; unwrap before use. The requirement key
// contains a dot ("residence.total_absences") and arrives percent-safe, but decode it
// anyway so a key needing escaping still resolves.
export default async function RequirementPage({
  params,
}: {
  params: Promise<{ caseId: string; requirementKey: string }>;
}) {
  const { caseId, requirementKey } = await params;
  return (
    <main style={{ maxWidth: "52rem", margin: "0 auto", padding: "var(--cw-space-8)" }}>
      <RequirementDetail caseId={caseId} requirementKey={decodeURIComponent(requirementKey)} />
    </main>
  );
}
