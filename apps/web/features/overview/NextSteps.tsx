import type { components } from "@cw/api-client";
import type { JSX } from "react";

type Overview = components["schemas"]["CaseOverview"];
type Destination = components["schemas"]["Destination"];

/** The id `PriorityActions` puts on its section, so a step can point at the cards. */
export const PRIORITY_ACTIONS_ID = "priority-actions";

/**
 * Where each step's link goes. The server names a destination rather than a URL so it never
 * owns this app's routes.
 *
 * `REQUIREMENTS` is where Run assessment lives before anything is assessed: the header's
 * Update assessment control renders only once there are results, and the requirements
 * list's empty state renders only while there are none, so that button is the one certain
 * to be there when `RUN_ASSESSMENT` is shown.
 */
function hrefFor(caseId: string, destination: Destination): string {
  switch (destination) {
    case "CASE_DATA":
      return `/cases/${caseId}/data`;
    case "EVIDENCE":
      return `/cases/${caseId}/evidence`;
    case "REQUIREMENTS":
      return `/cases/${caseId}/requirements`;
    case "ISSUES":
      return `/cases/${caseId}/issues`;
    case "PRIORITY_ACTIONS":
      return `#${PRIORITY_ACTIONS_ID}`;
  }
}

/**
 * The case's next steps (ADR-0034): one answer to "what now", for a new case and a
 * returning one alike.
 *
 * It replaced Start here, which answered only until the first assessment and was static:
 * a date already set disappeared rather than showing as done, and the trips step read the
 * same with five trips as with none. Two answers to "what now" are worse than one, so the
 * requirements' own asks are a step here too, with their cards kept below as the detail.
 *
 * **Nothing here is decided in the client.** Which steps apply, their order, their wording
 * and what counts as done all arrive from the server's rules. This maps a destination to a
 * link and lays the list out.
 *
 * What it must not do:
 *
 * - **Tally.** Done items are statements of what the case holds, never "2 of 3" or a bar
 *   filling up (CLAUDE.md §2.6).
 * - **Finish.** When nothing is left the server says what this workspace does not check;
 *   there is no "you're ready" state to render (CLAUDE.md §2.7).
 */
export function NextSteps({ overview }: { overview: Overview }): JSX.Element {
  const { done, steps } = overview.next_steps;

  return (
    <section className="cw-next-steps" aria-labelledby="next-steps-heading">
      <h3 id="next-steps-heading">Next steps</h3>

      {/* Where the user left off, quietly, before what is left. The tick is decoration; the
          list's name says what the items are. */}
      {done.length > 0 ? (
        <ul className="cw-next-steps__done" aria-label="Already done">
          {done.map((item) => (
            <li key={item.code}>
              <span className="cw-next-steps__tick" aria-hidden="true">
                ✓
              </span>
              {item.text}
            </li>
          ))}
        </ul>
      ) : null}

      {/* Ordered, because the order is the rules' own: the date before the trips measured
          against it, the review before the assessment it would change. */}
      <ol className="cw-next-steps__list">
        {steps.map((step, index) => (
          <li
            key={step.code}
            className="cw-next-step"
            data-primary={index === 0 ? "true" : undefined}
          >
            <p className="cw-next-step__head">
              <a className="cw-next-step__title" href={hrefFor(overview.case_id, step.destination)}>
                {step.title}
              </a>
              {step.optional ? <span className="cw-next-step__optional">Optional</span> : null}
            </p>
            <p className="cw-next-step__body">{step.body}</p>
          </li>
        ))}
      </ol>

    </section>
  );
}
