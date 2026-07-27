import { CaseWorkspace } from "@/features/case-workspace/CaseWorkspace";

// Next 15 delivers route params as a promise; unwrap before use.
export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  return (
    <main style={{ maxWidth: "40rem", margin: "0 auto", padding: "var(--cw-space-8)" }}>
      <CaseWorkspace caseId={caseId} />
    </main>
  );
}
