import type { Metadata } from "next";
import type { JSX } from "react";

import { IssuesDestination } from "@/features/issues/IssuesDestination";

export const metadata: Metadata = {
  title: "Issues — Citizenship Workspace",
};

export default async function IssuesPage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}): Promise<JSX.Element> {
  const { caseId } = await params;
  return <IssuesDestination caseId={caseId} />;
}
