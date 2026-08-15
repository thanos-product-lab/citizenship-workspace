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

/**
 * Requirement titles for the document title, keyed by requirement key.
 *
 * The API is the source of truth for a requirement's title and the page renders that; this
 * map exists only so `generateMetadata` can name the page without a request. A key missing
 * here falls back to the generic title rather than guessing — the metadata layer has no
 * session and must never block on a fetch that could fail.
 */
export const REQUIREMENT_TITLES: Record<string, string> = {
  "route.adult_applicant": "Adult applicant",
  "route.supported_status": "Settled status",
  "route.standard_section_6_1": "Standard five-year route",
  "status.holding_period": "Settled-status holding period",
  "residence.qualifying_period": "Qualifying period",
  "residence.physical_presence_start_date": "Presence on the first day",
  "residence.total_absences": "Total absences",
  "residence.final_year_absences": "Final-year absences",
  "residence.travel_consistency": "Travel record consistency",
  "knowledge.life_in_uk": "Life in the UK test",
  "knowledge.english_language": "English language",
  "referees.first": "First referee",
  "referees.second": "Second referee",
  "character.review": "Good character",
  "preparation.case_complete": "Case readiness",
};
