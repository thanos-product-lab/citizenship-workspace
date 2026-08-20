import type { components } from "@cw/api-client";

type IssueQueue = components["schemas"]["IssueQueue"];
export type IssueGroup = IssueQueue["groups"][number];
export type Issue = IssueGroup["issues"][number];

/**
 * Action-group key → its heading, following UI/UX §10's instruction to group issues by
 * *what the user does about them* rather than by type or by severity name. A reader
 * scanning the queue is deciding what to pick up next, and "Confirm information" answers
 * that where "Action required" does not.
 */
const GROUP_HEADINGS: Record<string, string> = {
  RESOLVE_TO_CONTINUE: "Resolve to continue",
  CONFIRM_INFORMATION: "Confirm information",
  REVIEW_CAREFULLY: "Review carefully",
  FOR_YOUR_AWARENESS: "For your awareness",
};

export function groupHeading(key: string): string {
  return GROUP_HEADINGS[key] ?? key.toLowerCase().replaceAll("_", " ");
}
