import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
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

});
