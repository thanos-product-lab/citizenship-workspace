"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { JSX } from "react";

import { CASE_DESTINATIONS, activeSegment, destinationHref } from "./destinations";
import { useCaseOverview } from "./useCaseOverview";

/**
 * Local navigation for one case.
 *
 * **Links, not ARIA tabs.** These are separate pages with their own URLs, titles and
 * history entries, so `role="tab"` / `tablist` would be a lie told to assistive
 * technology: it promises interchangeable panels within one document and suppresses the
 * link semantics that make bookmarking, opening in a new tab and back/forward work. The
 * correct native construct is a `<nav>` of links with `aria-current="page"` — which is
 * also why there is no ARIA here beyond the landmark label and `aria-current`.
 *
 * The current destination is marked three ways — `aria-current`, a weight change and an
 * underline — because a colour shift alone fails the non-colour rule that applies to
 * every state in this product, not only assessment states.
 */
export function CaseNavigation({ caseId }: { caseId: string }): JSX.Element {
  const pathname = usePathname() ?? "";
  const active = activeSegment(pathname, caseId);
  const { data: overview } = useCaseOverview(caseId);
  const openIssues = overview?.open_issue_count ?? 0;

  return (
    <nav aria-label="Case navigation" className="cw-case-nav">
      <ul className="cw-case-nav__list">
        {CASE_DESTINATIONS.map((destination) => {
          const isCurrent = destination.segment === active;
          return (
            <li key={destination.segment || "overview"}>
              <Link
                href={destinationHref(caseId, destination.segment)}
                className="cw-case-nav__link"
                aria-current={isCurrent ? "page" : undefined}
              >
                {destination.label}
                {/* The count is inside the link text, not a floating badge, so a screen
                    reader announces "Issues 4" as one label rather than leaving the number
                    orphaned. Absent at zero: a "0" is visual noise that reads as a state. */}
                {destination.segment === "issues" && openIssues > 0 ? (
                  <span className="cw-nav-count">
                    {openIssues}
                    <span className="cw-visually-hidden">
                      {openIssues === 1 ? " open issue" : " open issues"}
                    </span>
                  </span>
                ) : null}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
