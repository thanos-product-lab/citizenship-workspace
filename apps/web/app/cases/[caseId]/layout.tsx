import type { ReactNode } from "react";

import { CaseChrome } from "@/features/case-workspace/CaseChrome";

/**
 * The workspace shell for one case.
 *
 * A real route layout rather than a component each page renders, so the header and
 * navigation persist across a move between destinations instead of remounting. Every
 * page under `/cases/[caseId]` — including a requirement detail — sits inside it, which
 * is what keeps the case identity and its currency visible wherever the user is.
 */
export default async function CaseLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ caseId: string }>;
}) {
  // Next 15 delivers route params as a promise; unwrap before use.
  const { caseId } = await params;
  return (
    <main className="cw-workspace">
      <CaseChrome caseId={caseId}>{children}</CaseChrome>
    </main>
  );
}
