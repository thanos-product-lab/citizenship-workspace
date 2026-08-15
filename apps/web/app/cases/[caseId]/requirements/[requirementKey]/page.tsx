import type { Metadata } from "next";

import { RequirementDetail } from "@/features/requirements/RequirementDetail";
import { REQUIREMENT_TITLES } from "@/features/requirements/groups";

type Params = Promise<{ caseId: string; requirementKey: string }>;

/**
 * A distinct document title per requirement (WCAG 2.4.2). These are full navigations, so
 * the title is the first thing a screen-reader user hears on arrival and the only label in
 * tab and history lists — five requirements all titled "Citizenship Workspace" is five
 * indistinguishable entries.
 *
 * Derived from the key already in the URL rather than fetched: metadata runs on the server
 * with no Clerk session, and the title must not depend on a request that could fail.
 */
export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { requirementKey } = await params;
  const key = decodeURIComponent(requirementKey);
  const title = REQUIREMENT_TITLES[key];
  return { title: title ? `${title} — Citizenship Workspace` : "Citizenship Workspace" };
}

// Next 15 delivers route params as a promise; unwrap before use. The requirement key
// contains a dot ("residence.total_absences") and arrives percent-safe, but decode it
// anyway so a key needing escaping still resolves.
export default async function RequirementPage({ params }: { params: Params }) {
  const { caseId, requirementKey } = await params;
  return (
    <main style={{ maxWidth: "52rem", margin: "0 auto", padding: "var(--cw-space-8)" }}>
      <RequirementDetail caseId={caseId} requirementKey={decodeURIComponent(requirementKey)} />
    </main>
  );
}
