import type { components } from "@cw/api-client";

type Requirement = components["schemas"]["RequirementSummary"];

/**
 * Display labels for the requirement groups seeded in the catalogue (migration 0007).
 * The group *keys* are the contract; these labels are presentation only, which is why
 * they live here and not in the API.
 */
export const GROUP_LABELS: Record<string, string> = {
  ROUTE_AND_STATUS: "Identity and status",
  RESIDENCE: "Residence",
  KNOWLEDGE_AND_LANGUAGE: "Knowledge and language",
  REFEREES: "Referees",
  CHARACTER_AND_DECLARATIONS: "Character and declarations",
  PREPARATION: "Application preparation",
};

export interface RequirementGroup {
  key: string;
  items: Requirement[];
}

/**
 * Group requirements by `group_key`, preserving the server's `display_order` both within
 * a group and between groups.
 *
 * Order comes from the server rather than from `GROUP_LABELS`, so a group added to the
 * catalogue appears in its intended position even before it has a label here — an
 * unlabelled group falls back to its key rather than vanishing from the page.
 */
export function groupRequirements(requirements: Requirement[]): RequirementGroup[] {
  const ordered = [...requirements].sort((a, b) => a.display_order - b.display_order);
  const groups: RequirementGroup[] = [];
  for (const requirement of ordered) {
    const existing = groups.find((group) => group.key === requirement.group_key);
    if (existing) {
      existing.items.push(requirement);
    } else {
      groups.push({ key: requirement.group_key, items: [requirement] });
    }
  }
  return groups;
}
