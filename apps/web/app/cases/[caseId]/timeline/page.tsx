import type { Metadata } from "next";
import type { JSX } from "react";

import { TimelineDestination } from "@/features/timeline/TimelineDestination";

export const metadata: Metadata = {
  title: "Timeline — Citizenship Workspace",
};

export default async function TimelinePage({
  params,
}: {
  params: Promise<{ caseId: string }>;
}): Promise<JSX.Element> {
  const { caseId } = await params;
  return <TimelineDestination caseId={caseId} />;
}
