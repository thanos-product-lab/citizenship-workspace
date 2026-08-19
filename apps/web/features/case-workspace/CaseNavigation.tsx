"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { JSX } from "react";

import { CASE_DESTINATIONS, activeSegment, destinationHref } from "./destinations";

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
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
