import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
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

  it("derives the heading from the case phase, not from a verdict it invented", () => {
    render(<CaseOverviewPanel overview={anOverview({ current_phase: "BUILDING_CASE" })} />);
    expect(
      screen.getByRole("heading", { name: "Your case is taking shape" }),
    ).toBeInTheDocument();
  });

  it("names where the outstanding work is, from a count comparison", () => {
    render(<CaseOverviewPanel overview={anOverview()} />);
    expect(screen.getByText(/Of the requirements that need attention, most are in/)).toBeInTheDocument();
    expect(screen.getByText("Residence")).toBeInTheDocument();
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

  it("surfaces staleness at case level", () => {
    render(<CaseOverviewPanel overview={anOverview({ stale: 5 })} />);
    expect(screen.getByText(/5 conclusions have not been rechecked/)).toBeInTheDocument();
    expect(screen.getByText(/shown as they were reached, marked stale/)).toBeInTheDocument();
  });

  it("says nothing about staleness when nothing is stale", () => {
    render(<CaseOverviewPanel overview={anOverview({ stale: 0 })} />);
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

    const link = screen.getByRole("link", { name: "Presence on the first day" });
    expect(link).toHaveAttribute(
      "href",
      "/cases/c1/requirements/residence.physical_presence_start_date",
    );
    expect(
      screen.getByText(/This requirement cannot be satisfied until this is resolved/),
    ).toBeInTheDocument();
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
    // system has already flagged as not rechecked. Unlike a group tile, an action card has
    // no second badge — if the card says nothing, "cannot be satisfied until this is
    // resolved" reads as a settled fact.
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
    expect(
      screen.getByText(/haven’t been rechecked since your inputs changed/),
    ).toBeInTheDocument();
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
    expect(screen.queryByText(/haven’t been rechecked/)).not.toBeInTheDocument();
  });

  it("scopes the attention claim when requirements remain unassessed", () => {
    // "Most of the outstanding work" was a claim about the whole case computed only over
    // assessed requirements with a severe conclusion — it excluded every unassessed one.
    render(<CaseOverviewPanel overview={anOverview({ not_yet_assessed: 6 })} />);
    expect(
      screen.getByText(/Requirements that haven’t been assessed yet aren’t counted here/),
    ).toBeInTheDocument();
  });

  it("pairs each header fact with its value in a description list", () => {
    // dt/dd outside a dl lose the pairing entirely; the proposed application date would
    // read as two unrelated fragments.
    const { container } = render(<CaseOverviewPanel overview={anOverview()} />);
    const dl = container.querySelector("dl.cw-overview__facts");
    expect(dl).not.toBeNull();
    expect(dl?.querySelectorAll("dt")).toHaveLength(3);
    expect(dl?.querySelectorAll("dd")).toHaveLength(3);
  });

  it("names the counts list so the numbers are not announced bare", () => {
    render(<CaseOverviewPanel overview={anOverview()} />);
    expect(screen.getByRole("list", { name: "Requirements by state" })).toBeInTheDocument();
  });

  it("says the figures are out of date while a refetch is in flight", () => {
    // The window after a write and before the refetch lands is one where the summary shows
    // pre-write counts. Silence there is a summary presenting superseded numbers as
    // current — the same failure as a stale badge that never appears.
    render(<CaseOverviewPanel overview={anOverview()} updating />);
    expect(
      screen.getByText("Updating — these figures are from before your last change."),
    ).toBeInTheDocument();
  });

  it("says nothing about updating when no refetch is in flight", () => {
    render(<CaseOverviewPanel overview={anOverview()} />);
    expect(screen.queryByText(/Updating —/)).not.toBeInTheDocument();
  });

  it("omits the actions section entirely when there is nothing to do", () => {
    render(<CaseOverviewPanel overview={anOverview({ priority_actions: [] })} />);
    expect(screen.queryByRole("heading", { name: "What to do next" })).not.toBeInTheDocument();
  });

  it("renders a case with no application date", () => {
    const { container } = render(
      <CaseOverviewPanel
        overview={anOverview({ application_date: null, last_assessed_at: null })}
      />,
    );
    expect(screen.queryByText("Proposed application date")).not.toBeInTheDocument();
    expect(within(container).getByText("Standard five-year route")).toBeInTheDocument();
  });
});
