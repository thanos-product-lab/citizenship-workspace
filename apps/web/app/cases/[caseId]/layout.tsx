import type { ReactNode } from "react";

import { CaseChrome } from "@/features/case-workspace/CaseChrome";
import { MAIN_LANDMARK_ID } from "@/features/case-workspace/destinations";

/**
 * The workspace shell for one case.
 *
 * A real route layout rather than a component each page renders, so the header and
 * navigation persist across a move between destinations instead of remounting. Every
 * page under `/cases/[caseId]` — including a requirement detail — sits inside it, which
 * is what keeps the case identity and its currency visible wherever the user is.
 *
 * **No `<main>` here, and no width.** Both moved into `CaseChrome`. The case header is
 * persistent context rather than page content, so wrapping it in `<main>` put it inside
 * the landmark that "skip to main content" is supposed to skip past. And the shell's
 * bands — the tinted identity, the navigation rule — have to reach the viewport edges
 * while their contents stay in a readable column, which a single width-constrained
 * wrapper cannot express.
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
    <div className="cw-workspace">
      {/* WCAG 2.4.1 Bypass Blocks. Every destination repeats seven tabbable controls
          before its own content — the back link, Update assessment and six navigation
          links — so reaching a requirement row costs eight presses, on every page, for
          ever. The landmarks satisfy the criterion for anyone navigating by landmark; a
          keyboard user without a screen reader had no bypass at all.

          Rendered here rather than inside `CaseChrome` for two reasons: the layout is a
          server component, so this is the first tabbable in the document without waiting
          on a fetch, and it stays present on every lifecycle branch — including the ones
          that render an error, where a user is most likely to be tabbing around looking
          for a way out. */}
      <a className="cw-skip-link" href={`#${MAIN_LANDMARK_ID}`}>
        Skip to main content
      </a>
      <CaseChrome caseId={caseId}>{children}</CaseChrome>
    </div>
  );
}
