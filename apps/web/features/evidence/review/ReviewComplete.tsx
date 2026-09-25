"use client";

import Link from "next/link";
import type { JSX } from "react";

import { useCaseOverview } from "@/features/case-workspace/useCaseOverview";
import {
  useRecalculate,
  useRecalculationInFlight,
} from "@/features/case-workspace/useRecalculate";

import type { ReviewClaim } from "./useDocumentClaims";

/** The id `DocumentReview` moves focus to when the last value is decided. */
export const REVIEW_COMPLETE_ID = "review-complete";

/**
 * What the reviewer is told once every value on a document has been decided.
 *
 * Before this, the page said "All N values have been decided." and stopped: no record of
 * what was decided, no way back to the library but the header link, and nothing about
 * the assessment. A review is the one place a proposal becomes a fact, so its end is
 * worth stating properly.
 *
 * **The stale count is the case's, not this document's.** The overview carries how many
 * conclusions are stale, not which input staled each one, so the sentence says the case
 * has conclusions waiting rather than claiming this review caused them. Deciding a travel
 * date does stale the residence results in the same transaction (`facts.service.
 * _invalidate_dependents`), so after a date review the two usually coincide, but the
 * wording has to be true when they do not.
 */
export function ReviewComplete({
  caseId,
  claims,
}: {
  caseId: string;
  claims: readonly ReviewClaim[];
}): JSX.Element {
  const { data: overview } = useCaseOverview(caseId);
  // Its own observer, so its own announcement and failure. The header's button reports
  // only the runs it started, and a run started here would otherwise finish in silence.
  const { mutation: recalculate, announcement } = useRecalculate(caseId);
  const inFlight = useRecalculationInFlight(caseId);
  const busy = inFlight || recalculate.isPending;

  const count = (decision: string) =>
    claims.filter((claim) => claim.decision?.decision === decision).length;
  const rejected = count("REJECT");
  const tally = [
    [count("CONFIRM"), "confirmed"],
    [count("CORRECT"), "corrected"],
    [rejected, "rejected"],
  ]
    .filter(([n]) => n !== 0)
    .map(([n, word]) => `${n} ${word}`)
    .join(" · ");

  const stale = overview?.stale ?? 0;

  return (
    <section
      id={REVIEW_COMPLETE_ID}
      // Programmatic focus only, so a keyboard user lands on the outcome and the next
      // step rather than on the last field they happened to decide.
      tabIndex={-1}
      className="cw-review-complete"
      aria-labelledby={`${REVIEW_COMPLETE_ID}-heading`}
    >
      <h2 id={`${REVIEW_COMPLETE_ID}-heading`} className="cw-review-complete__heading">
        Review complete
      </h2>
      <p className="cw-review-complete__tally">{tally}.</p>
      {rejected > 0 ? (
        <p className="cw-review-complete__note">
          {rejected === 1 ? "The rejected value was" : "Rejected values were"} not used. That
          is a finished decision, and nothing is waiting on it.
        </p>
      ) : null}

      {stale > 0 ? (
        <p className="cw-review-complete__note">
          {stale === 1
            ? "1 conclusion in your case has"
            : `${stale} conclusions in your case have`}{" "}
          not been rechecked since your inputs changed.
        </p>
      ) : null}

      <div className="cw-review-complete__actions">
        {stale > 0 ? (
          <button
            type="button"
            className="cw-button"
            onClick={() =>
              busy
                ? undefined
                : recalculate.mutate(undefined, {
                    // The button unmounts once the run clears the stale count, taking
                    // focus to `<body>` with it. The panel is still here and still says
                    // what to do next, so focus goes back to it.
                    onSettled: () =>
                      requestAnimationFrame(() =>
                        document.getElementById(REVIEW_COMPLETE_ID)?.focus(),
                      ),
                  })
            }
            aria-disabled={busy}
          >
            {busy ? "Updating…" : "Update assessment"}
          </button>
        ) : null}
        <Link
          className={`cw-button${stale > 0 ? " cw-button--secondary" : ""}`}
          href={`/cases/${caseId}/evidence`}
        >
          Return to evidence
        </Link>
      </div>

      <p aria-live="polite" className="cw-visually-hidden">
        {announcement}
      </p>
      {recalculate.isError ? (
        <p role="alert" className="cw-case-header__error">
          The update didn’t finish. The page shows what was saved before it.
        </p>
      ) : null}
    </section>
  );
}
