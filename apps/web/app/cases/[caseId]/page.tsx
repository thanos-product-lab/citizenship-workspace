import { RouteOnboarding } from "@/features/onboarding/RouteOnboarding";

// Next 15 delivers route params as a promise; unwrap before use.
export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  return (
    <main style={{ maxWidth: "40rem", margin: "0 auto", padding: "var(--cw-space-8)" }}>
      <a href="/" style={{ color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        ← Your cases
      </a>
      <RouteOnboarding caseId={caseId} />
    </main>
  );
}
