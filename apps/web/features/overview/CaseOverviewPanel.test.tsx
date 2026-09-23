import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { CaseOverviewPanel } from "./CaseOverviewPanel";

function aGroup(overrides: Record<string, unknown> = {}) {
  return {
    group_key: "RESIDENCE",
    conclusion_counts: [
      { conclusion: "NOT_CURRENTLY_SATISFIED", count: 1 },
      { conclusion: "NEAR_THRESHOLD", count: 1 },
      { conclusion: "SUPPORTED", count: 3 },
    ],
    not_yet_assessed: 0,
    total: 5,
    currency: "CURRENT",
    needs_attention: 1,
    stale: 0,
    is_fully_concluded: true,
    requirements: [
      {
        requirement_key: "residence.total_absences",
        title: "Total absences",
        conclusion: "NEAR_THRESHOLD",
        currency: "CURRENT",
      },
    ],
    ...overrides,
  };
}

function anOverview(overrides: Record<string, unknown> = {}) {
  return {
    case_id: "c1",
    title: "Amara Okonkwo — demo",
    route_key: "SECTION_6_1_STANDARD",
    lifecycle_status: "ACTIVE",
    current_phase: "RESOLVING_ISSUES",
    application_date: "2027-04-15",
    application_date_has_passed: false,
    groups: [
      aGroup(),
      aGroup({
        group_key: "REFEREES",
        conclusion_counts: [],
        not_yet_assessed: 2,
        total: 2,
        currency: null,
        needs_attention: 0,
        is_fully_concluded: false,
        requirements: [],
      }),
    ],
    priority_actions: [],
    priority_actions_hidden: 0,
    conclusion_counts: [
      { conclusion: "NOT_CURRENTLY_SATISFIED", count: 1 },
      { conclusion: "NEAR_THRESHOLD", count: 1 },
      { conclusion: "SUPPORTED", count: 3 },
    ],
    not_yet_assessed: 2,
    needs_attention: 1,
    stale: 0,
    open_issue_count: 0,
    issue_action_count: 0,
    total_requirements: 7,
    last_assessed_at: "2026-08-14T11:36:00Z",
    ...overrides,
  };
}

describe("CaseOverviewPanel", () => {
  it("shows no percentage, score, or fraction anywhere", () => {
    // CLAUDE.md §2.6. The payload carries `total` and `not_yet_assessed` precisely so the
    // UI can say what has NOT been assessed — rendering them as "5 of 7" would produce a
    // completion measure sideways, which is the thing the invariant forbids.
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/%/);
    expect(text).not.toMatch(/\b\d+\s*(of|\/)\s*\d+\b/);
    expect(text).not.toMatch(/complete|progress|readiness score/i);
  });

  it("says the application date has passed, above the figures it qualifies", () => {
    /**
     * `KNOWN_LIMITATIONS.md` 11. A case left alone until its date went by read as
     * supported against a window that had already closed — the false-reassurance shape
     * §2.7 ranks as the most important thing to get right.
     *
     * Above the counts on purpose: it qualifies every one of them, and a reader who meets
     * the caveat after the figures has already taken the figures at face value.
     */
    const { container } = render(
      <CaseOverviewPanel
        overview={anOverview({
          application_date: "2026-04-15",
          application_date_has_passed: true,
        })}
      />,
    );

    const notice = container.querySelector(".cw-date-passed-notice");
    expect(notice).not.toBeNull();
    expect(notice?.textContent).toMatch(/15 April 2026/);
    expect(notice?.textContent).toMatch(/has passed/);
    // Never "wrong", "invalid" or "out of date": the arithmetic is correct about a period
    // that is over, and saying otherwise would be its own false statement.
    expect(notice?.textContent).not.toMatch(/wrong|invalid|out of date|no longer valid/i);
    // It sits before the counts in document order.
    const counts = container.querySelector(".cw-overview__counts");
    expect(notice?.compareDocumentPosition(counts as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("says nothing when the date is still ahead", () => {
    // The default fixture is a 2027 date with the flag false. A notice here would be
    // crying wolf on every healthy case.
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    expect(container.querySelector(".cw-date-passed-notice")).toBeNull();
  });

  it("states counts by named state, most severe first", () => {
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    const order = Array.from(container.querySelectorAll(".cw-overview__counts li")).map(
      (li) => li.textContent?.replace(/\d+\s*/, "").trim(),
    );
    // Severity order, not magnitude: "supported" has the largest count and comes last.
    expect(order).toEqual([
      "not currently satisfied",
      "near threshold",
      "supported",
      "not yet assessed",
    ]);
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("supported")).toBeInTheDocument();
    expect(screen.getByText("near threshold")).toBeInTheDocument();
    expect(screen.getByText("not currently satisfied")).toBeInTheDocument();
  });

  it("states the unassessed count as its own fact, not as a remainder", () => {
    render(<CaseOverviewPanel overview={anOverview()} />);
    expect(screen.getByText("not yet assessed")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("leads with the count of requirements needing attention, from the server", () => {
    // Not a bucket assembled here: `needs_attention` excludes NEAR_THRESHOLD, which sits
    // below the attention boundary. Grouping the blocker with the near-threshold one
    // would read "2" and disagree with the engine and with the phase pill above.
    render(<CaseOverviewPanel overview={anOverview({ needs_attention: 1 })} />);
    expect(
      screen.getByRole("heading", { name: "1 requirement needs your attention", level: 2 }),
    ).toBeInTheDocument();
  });

  it("pluralises the headline and never invents a count", () => {
    render(<CaseOverviewPanel overview={anOverview({ needs_attention: 3 })} />);
    expect(
      screen.getByRole("heading", { name: "3 requirements need your attention" }),
    ).toBeInTheDocument();
  });

  it("scopes the all-clear while requirements remain unassessed", () => {
    // "Nothing needs your attention" would be an all-clear the engine has not given while
    // six requirements have never been looked at.
    render(<CaseOverviewPanel overview={anOverview({ needs_attention: 0, not_yet_assessed: 6 })} />);
    expect(
      screen.getByRole("heading", { name: "Nothing assessed so far needs your attention" }),
    ).toBeInTheDocument();
  });

  it("gives a plain all-clear only when everything has been assessed", () => {
    render(<CaseOverviewPanel overview={anOverview({ needs_attention: 0, not_yet_assessed: 0 })} />);
    expect(
      screen.getByRole("heading", { name: "Nothing needs your attention" }),
    ).toBeInTheDocument();
  });

  it("says so when the case has not been assessed at all", () => {
    render(
      <CaseOverviewPanel
        overview={anOverview({ conclusion_counts: [], needs_attention: 0, not_yet_assessed: 15 })}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "This case hasn’t been assessed yet" }),
    ).toBeInTheDocument();
  });

  it("does not restate the case phase — the pill beside the title carries it", () => {
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    expect(container.textContent).not.toMatch(/taking shape|work to do on your case/i);
  });

  it("names where the outstanding work is, from a count comparison", () => {
    const overview = anOverview({
      priority_actions: [
        {
          requirement_key: "residence.physical_presence_start_date",
          requirement_title: "Presence on the first day",
          conclusion: "NOT_CURRENTLY_SATISFIED",
          code: "SELECT_APPLICATION_DATE",
          parameters: {},
          currency: "CURRENT",
          text: "Consider moving your proposed application date to 25 April 2027.",
          blocking: true,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);
    expect(screen.getByText(/Most of what needs attention is in Residence/)).toBeInTheDocument();
  });

  it("says nothing about where the work is when nothing needs attention", () => {
    // Silence rather than a reassuring sentence: "everything looks fine" is a verdict.
    const clean = anOverview({
      groups: [
        aGroup({ needs_attention: 0, conclusion_counts: [{ conclusion: "SUPPORTED", count: 5 }] }),
      ],
      conclusion_counts: [{ conclusion: "SUPPORTED", count: 5 }],
    });
    render(<CaseOverviewPanel overview={clean} />);
    expect(screen.queryByText(/most are in/)).not.toBeInTheDocument();
  });

  it("leaves currency to the case header, which every destination shows", () => {
    // Staleness is caused by editing an input under Case data, so the signal has to
    // follow the user rather than living on this page. Duplicating it here would put the
    // same claim in two places and let them drift.
    render(<CaseOverviewPanel overview={anOverview({ stale: 5 })} />);
    expect(screen.queryByText(/have not been rechecked/)).not.toBeInTheDocument();
  });

  it("shows at most three actions and says how many it is not showing", () => {
    const overview = anOverview({
      priority_actions: [1, 2, 3].map((i) => ({
        requirement_key: `r.${i}`,
        requirement_title: `Requirement ${i}`,
        conclusion: "NOT_CURRENTLY_SATISFIED",
        code: "SELECT_APPLICATION_DATE",
        parameters: {},
        currency: "CURRENT",
        text: `Do thing ${i}.`,
        blocking: false,
      })),
      priority_actions_hidden: 2,
    });
    render(<CaseOverviewPanel overview={overview} />);

    expect(screen.getAllByText(/Do thing/)).toHaveLength(3);
    expect(
      screen.getByText(/2 more actions aren’t shown here/),
    ).toBeInTheDocument();
  });

  it("links every action to the requirement that raised it", () => {
    const overview = anOverview({
      priority_actions: [
        {
          requirement_key: "residence.physical_presence_start_date",
          requirement_title: "Presence on the first day",
          conclusion: "NOT_CURRENTLY_SATISFIED",
          code: "SELECT_APPLICATION_DATE",
          parameters: { resolving_application_date: "2027-04-25" },
          currency: "CURRENT",
          text: "Consider moving your proposed application date to 25 April 2027.",
          blocking: true,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);

    const link = screen.getByRole("link", { name: /Review requirement/ });
    expect(link).toHaveAttribute(
      "href",
      "/cases/c1/requirements/residence.physical_presence_start_date",
    );
    // The requirement's own conclusion, not a "Blocking" chip standing in for one.
    expect(screen.getByText("Not currently satisfied")).toBeInTheDocument();
    // Blocking is stated once, as the action's meta.
    expect(screen.getByText("Blocks this requirement")).toBeInTheDocument();
  });

  it("renders the server's action text, never a code", () => {
    const overview = anOverview({
      priority_actions: [
        {
          requirement_key: "x.y",
          requirement_title: "X",
          conclusion: "INCOMPLETE",
          code: "SELECT_APPLICATION_DATE",
          parameters: {},
          currency: "CURRENT",
          text: "Consider moving your proposed application date to 25 April 2027.",
          blocking: false,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);
    expect(screen.getByText(/Consider moving your proposed application date/)).toBeInTheDocument();
    expect(screen.queryByText("SELECT_APPLICATION_DATE")).not.toBeInTheDocument();
  });

  it("marks an action derived from a stale result", () => {
    // Displayed results include STALE, so an action can be computed from arithmetic the
    // system has flagged as not rechecked. The card now carries the requirement's own
    // conclusion *and* currency, which is the per-item badge that was missing before.
    const overview = anOverview({
      priority_actions: [
        {
          requirement_key: "residence.physical_presence_start_date",
          requirement_title: "Presence on the first day",
          conclusion: "NOT_CURRENTLY_SATISFIED",
          code: "SELECT_APPLICATION_DATE",
          parameters: {},
          currency: "STALE",
          text: "Consider moving your proposed application date to 25 April 2027.",
          blocking: true,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByText("Not currently satisfied")).toBeInTheDocument();
  });

  it("does not mark a current action as stale", () => {
    const overview = anOverview({
      priority_actions: [
        {
          requirement_key: "x.y",
          requirement_title: "X",
          conclusion: "INCOMPLETE",
          code: "SELECT_APPLICATION_DATE",
          parameters: {},
          currency: "CURRENT",
          text: "Do the thing.",
          blocking: false,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  });

  it("scopes the attention claim when requirements remain unassessed", () => {
    // The comparison runs over assessed requirements with a severe conclusion only, so
    // without this bound it reads as a claim about the whole case.
    const overview = anOverview({
      not_yet_assessed: 6,
      priority_actions: [
        {
          requirement_key: "x.y",
          requirement_title: "X",
          conclusion: "NOT_CURRENTLY_SATISFIED",
          code: "SELECT_APPLICATION_DATE",
          parameters: {},
          currency: "CURRENT",
          text: "Do the thing.",
          blocking: false,
        },
      ],
    });
    render(<CaseOverviewPanel overview={overview} />);
    expect(
      screen.getByText(/Requirements that haven’t been assessed yet aren’t counted/),
    ).toBeInTheDocument();
  });

  it("leaves case metadata to the header", () => {
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    expect(container.querySelector("dl")).toBeNull();
    expect(screen.queryByText("Proposed application date")).not.toBeInTheDocument();
  });

  it("names the counts list so the numbers are not announced bare", () => {
    render(<CaseOverviewPanel overview={anOverview()} />);
    expect(screen.getByRole("list", { name: "Requirements by state" })).toBeInTheDocument();
  });

  it("omits the actions section entirely when there is nothing to do", () => {
    render(<CaseOverviewPanel overview={anOverview({ priority_actions: [] })} />);
    expect(screen.queryByRole("heading", { name: "What to do next" })).not.toBeInTheDocument();
  });


/**
 * The automated floor for this flow (release slice, accessibility pass).
 *
 * axe finds the mechanical failures — an unlabelled control, a broken ARIA reference, a
 * heading level skipped, a contrast pair below ratio. It cannot find the ones this project
 * has actually shipped: a label that told a user to act before the screen to act on
 * existed, a live region overwritten 38ms after it was written, a status distinguished only
 * by hue. Those come from the keyboard and greyscale passes. This stops the mechanical ones
 * reaching them.
 */
  it("has no axe violations", async () => {
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    expect(await axe(container)).toHaveNoViolations();
  });

  describe("a case nothing has assessed yet", () => {
    /**
     * The walkthrough finding. The screen said "This case hasn't been assessed yet", then
     * six group rows each repeating "not yet assessed", and stopped — every word true and
     * none of it a next step, because `priority_actions` derives from results and a case
     * with no results has none.
     */
    function anUnassessedOverview(overrides: Record<string, unknown> = {}) {
      return anOverview({
        conclusion_counts: [],
        needs_attention: 0,
        not_yet_assessed: 15,
        priority_actions: [],
        application_date: null,
        ...overrides,
      });
    }

    it("tells the user where to start", () => {
      render(<CaseOverviewPanel overview={anUnassessedOverview()} />);

      const start = screen.getByRole("region", { name: "Start here" });
      expect(within(start).getByRole("link", { name: /Set the date you plan to apply/ }))
        .toHaveAttribute("href", "/cases/c1/data");
      expect(within(start).getByRole("link", { name: /periods you spent outside the UK/ }))
        .toHaveAttribute("href", "/cases/c1/data");
    });

    it("sends the last step to a control that exists in this state", () => {
      /**
       * The step used to read "Then choose **Recalculate** above", and that button was
       * guaranteed to be absent whenever this list was on screen. `RecalculateButton`
       * renders only when `assessed > 0`; this block renders only when `assessed === 0`.
       * Two components keyed off one predicate in exact opposition, so the instruction was
       * wrong every time it was shown.
       *
       * It pointed at nothing by name, too: the header control is labelled "Update
       * assessment", argued for deliberately in `CaseHeader`.
       *
       * The requirements list's empty state fires on `withResults.length === 0`, which is
       * this same condition, so its "Run assessment" is the one control certain to be
       * there. Asserting the destination is what keeps the pair from drifting apart again.
       */
      render(<CaseOverviewPanel overview={anUnassessedOverview()} />);

      const start = screen.getByRole("region", { name: "Start here" });
      expect(within(start).getByRole("link", { name: "Requirements" })).toHaveAttribute(
        "href",
        "/cases/c1/requirements",
      );
      expect(start).toHaveTextContent(/Run assessment/);
      expect(start).not.toHaveTextContent(/Recalculate/);
    });

    it("stops offering the application date once the case has one", () => {
      /**
       * **A date with no conclusions, which is a real state and not an arrangement of the
       * fixture.** Worth saying, because the pair looks impossible from inside this app: the
       * only control that saves a date is `ApplicationDateCard`, and it selects and
       * recalculates in one action, so a user of the web form never sees it.
       *
       * It arises two ways. `POST /application-dates/select` with no following
       * `/assessments/recalculate` produces it directly — pairing them is a convention of
       * `useSaveApplicationDate`, not something the API requires, so any other client
       * reaches this in one call. And when the recalculation half of that pair fails, the
       * user is left here with a saved date and nothing assessed, which is exactly the
       * moment the list below has to be right.
       *
       * Observed live rather than reasoned about: case `c128470c`, date saved, fifteen
       * requirements unassessed, this two-step list on screen.
       */
      render(<CaseOverviewPanel overview={anUnassessedOverview({ application_date: "2027-04-15" })} />);

      const start = screen.getByRole("region", { name: "Start here" });
      expect(within(start).queryByRole("link", { name: /Set the date you plan to apply/ })).toBeNull();
      expect(within(start).getByRole("link", { name: /periods you spent outside the UK/ })).toBeTruthy();
      // The remaining steps still have to be a complete instruction on their own.
      expect(within(start).getAllByRole("listitem")).toHaveLength(2);
      expect(start).toHaveTextContent(/Run assessment/);
    });

    it("orders the steps, because the window is measured back from the date", () => {
      // A list, not a set of cards: travel entered before there is an application date has
      // no qualifying period to sit in, so the sequence is the information.
      render(<CaseOverviewPanel overview={anUnassessedOverview()} />);
      const items = within(screen.getByRole("region", { name: "Start here" })).getAllByRole("listitem");
      expect(items).toHaveLength(3);
      expect(items[0]).toHaveTextContent(/Set the date you plan to apply/);
    });

    it("disappears the moment anything has been assessed", () => {
      // Two answers to "what now" is worse than the one that was missing: once there are
      // results, `Needs your attention` is the answer.
      render(<CaseOverviewPanel overview={anOverview()} />);
      expect(screen.queryByRole("region", { name: "Start here" })).toBeNull();
    });

    it("still shows no score, fraction or percentage", () => {
      // The rule the empty state must not quietly break: "15 not yet assessed" beside
      // three steps is a count and a sequence, never progress through them.
      const { container } = render(<CaseOverviewPanel overview={anUnassessedOverview()} />);
      expect(container.textContent).not.toMatch(/%|\d+\s*\/\s*\d+|\bof 15\b/);
    });
  });
});
