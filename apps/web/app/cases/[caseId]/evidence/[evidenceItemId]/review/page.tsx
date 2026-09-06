import type { Metadata } from "next";

import { ReviewDestination } from "@/features/evidence/review/ReviewDestination";

type Params = Promise<{ caseId: string; evidenceItemId: string }>;

/**
 * A distinct title, for the reason the requirement sub-page gives: this is a full
 * navigation, so the title is the first thing a screen-reader user hears on arrival.
 *
 * The document's own name is deliberately **not** in it. Metadata runs on the server with
 * no Clerk session, so it cannot be fetched — and a title is written into browser history
 * and tab lists, which is a poor place for a user's own words about their document.
 */
export const metadata: Metadata = {
  title: "Confirm what we read — Citizenship Workspace",
};

export default async function DocumentReviewPage({ params }: { params: Params }) {
  const { caseId, evidenceItemId } = await params;
  // No <main>: the case layout owns the landmark, the header and the navigation. This is
  // a sub-page of Evidence, and `activeSegment` matches on the first segment, so the nav
  // keeps Evidence marked current while it is open.
  return <ReviewDestination caseId={caseId} evidenceItemId={evidenceItemId} />;
}
