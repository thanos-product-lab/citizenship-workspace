import "@testing-library/jest-dom/vitest";

import type { components } from "@cw/api-client";
import { render, screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { CaseOverviewPanel } from "./CaseOverviewPanel";

// Typed, because its codes are enums in the generated client and a bare literal widens.
const DEFAULT_NEXT_STEPS: components["schemas"]["NextStepsView"] = {
  done: [
    { code: "DATE_SET", text: "Application date set: 15 April 2027" },
    { code: "TRIPS_RECORDED", text: "5 trips recorded" },
    { code: "ASSESSED", text: "Assessed on 14 August 2026" },
  ],
  steps: [
    {
      code: "RESOLVE_REQUIREMENTS",
      destination: "PRIORITY_ACTIONS",
      parameters: { count: 2 },
      title: "See what your requirements ask of you",
      body: "2 things are listed below.",
      optional: false,
    },
    {
      code: "ATTACH_TRIP_EVIDENCE",
      destination: "CASE_DATA",
      parameters: { count: 3 },
      title: "Attach documents to your trips",
      body: "3 confirmed trips have no document attached. Nothing in your assessment depends on this.",
      optional: true,
    },
  ],
};

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
    next_steps: DEFAULT_NEXT_STEPS,
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

  describe("next steps", () => {
    /**
     * ADR-0034. The server decides which steps apply, their order and their words; the
     * panel renders them. These pin what the rendering adds: links, emphasis, the optional
     * label, the done list, and that it is the only answer to "what now".
     */
    const newCase = {
      conclusion_counts: [],
      needs_attention: 0,
      not_yet_assessed: 15,
      priority_actions: [],
      application_date: null,
      last_assessed_at: null,
      next_steps: {
        done: [],
        steps: [
          {
            code: "SET_APPLICATION_DATE",
            destination: "CASE_DATA",
            parameters: {},
            title: "Set your proposed application date",
            body: "Every residence check counts back from this date.",
            optional: false,
          },
          {
            code: "ADD_TRIPS",
            destination: "CASE_DATA",
            parameters: {},
            title: "Add your trips outside the UK",
            body: "The checks count your days outside the UK before your application date.",
            optional: false,
          },
        ],
      },
    };

    it("leads a new case with its first step, linked to where it is done", () => {
      render(<CaseOverviewPanel overview={anOverview(newCase)} />);
      const panel = screen.getByRole("region", { name: "Next steps" });
      const items = within(within(panel).getAllByRole("list").at(-1)!).getAllByRole("listitem");
      expect(items).toHaveLength(2);
      expect(items[0]).toHaveAttribute("data-primary", "true");
      expect(items[1]).not.toHaveAttribute("data-primary");
      expect(
        within(items[0]!).getByRole("link", { name: "Set your proposed application date" }),
      ).toHaveAttribute("href", "/cases/c1/data");
      // Nothing is done yet, so there is no done list to be empty.
      expect(within(panel).queryByRole("list", { name: "Already done" })).toBeNull();
    });

    it("is the only answer to what now: Start here is gone", () => {
      render(<CaseOverviewPanel overview={anOverview(newCase)} />);
      expect(screen.queryByRole("region", { name: "Start here" })).toBeNull();
    });

    it("says what is already done as statements, not a tally", () => {
      render(<CaseOverviewPanel overview={anOverview()} />);
      const done = screen.getByRole("list", { name: "Already done" });
      expect(within(done).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
        "✓Application date set: 15 April 2027",
        "✓5 trips recorded",
        "✓Assessed on 14 August 2026",
      ]);
    });

    it("labels an optional step in words", () => {
      render(<CaseOverviewPanel overview={anOverview()} />);
      const panel = screen.getByRole("region", { name: "Next steps" });
      const optional = within(panel)
        .getByRole("link", { name: "Attach documents to your trips" })
        .closest("li")!;
      expect(optional).toHaveTextContent("Optional");
      expect(optional).not.toHaveAttribute("data-primary");
    });

    it("points the requirements step at the cards, which still render beneath it", () => {
      render(
        <CaseOverviewPanel
          overview={anOverview({
            priority_actions: [
              {
                requirement_key: "residence.total_absences",
                requirement_title: "Total absences",
                conclusion: "NEAR_THRESHOLD",
                currency: "CURRENT",
                code: "SELECT_APPLICATION_DATE",
                parameters: {},
                text: "Consider moving your proposed application date.",
                blocking: false,
              },
            ],
          })}
        />,
      );
      expect(
        screen.getByRole("link", { name: "See what your requirements ask of you" }),
      ).toHaveAttribute("href", "#priority-actions");
      const cards = screen.getByRole("region", { name: "What your requirements ask" });
      expect(cards).toHaveAttribute("id", "priority-actions");
      expect(cards).toHaveTextContent("Consider moving your proposed application date.");
    });

    it("maps every destination to a route in this case", () => {
      const destinations = {
        CASE_DATA: "/cases/c1/data",
        EVIDENCE: "/cases/c1/evidence",
        REQUIREMENTS: "/cases/c1/requirements",
        ISSUES: "/cases/c1/issues",
        PRIORITY_ACTIONS: "#priority-actions",
      };
      for (const [destination, href] of Object.entries(destinations)) {
        const { unmount } = render(
          <CaseOverviewPanel
            overview={anOverview({
              next_steps: {
                done: [],
                steps: [
                  {
                    code: "OPEN_ISSUES",
                    destination,
                    parameters: {},
                    title: `Go ${destination}`,
                    body: "",
                    optional: false,
                  },
                ],
              },
            })}
          />,
        );
        expect(screen.getByRole("link", { name: `Go ${destination}` })).toHaveAttribute(
          "href",
          href,
        );
        unmount();
      }
    });

    it("has no axe violations on a new case", async () => {
      const { container } = render(<CaseOverviewPanel overview={anOverview(newCase)} />);
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
