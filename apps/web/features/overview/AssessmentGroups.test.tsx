import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssessmentGroups } from "./AssessmentGroups";

type Group = Record<string, unknown>;

function aGroup(overrides: Group = {}): Group {
  return {
    group_key: "RESIDENCE",
    conclusion_counts: [{ conclusion: "SUPPORTED", count: 4 }],
    not_yet_assessed: 0,
    total: 4,
    currency: "CURRENT",
    needs_attention: 0,
    stale: 0,
    is_fully_concluded: true,
    requirements: [],
    ...overrides,
  };
}

function anOverview(groups: Group[]) {
  return {
    case_id: "c1",
    title: "My case",
    route_key: "SECTION_6_1_STANDARD",
    lifecycle_status: "ACTIVE",
    current_phase: "RESOLVING_ISSUES",
    application_date: "2027-04-15",
    last_assessed_at: "2026-08-19T11:00:00Z",
    groups,
    conclusion_counts: [],
    priority_actions: [],
    priority_actions_hidden: 0,
    needs_attention: 0,
    not_yet_assessed: 0,
    stale: 0,
    open_issues: 0,
    total_requirements: 15,
    ...{},
  } as never;
}

/** The canonical case: 4 supported, then residence's mix, then five unassessed groups. */
function canonicalGroups(): Group[] {
  return [
    aGroup({
      group_key: "ROUTE_AND_STATUS",
      conclusion_counts: [{ conclusion: "SUPPORTED", count: 4 }],
      total: 4,
    }),
    aGroup({
      group_key: "RESIDENCE",
      conclusion_counts: [
        { conclusion: "NOT_CURRENTLY_SATISFIED", count: 1 },
        { conclusion: "NEAR_THRESHOLD", count: 1 },
        { conclusion: "SUPPORTED", count: 3 },
      ],
      total: 5,
      needs_attention: 1,
      is_fully_concluded: true,
    }),
    aGroup({
      group_key: "KNOWLEDGE_AND_LANGUAGE",
      conclusion_counts: [],
      not_yet_assessed: 2,
      total: 2,
      currency: null,
      is_fully_concluded: false,
    }),
  ];
}

describe("AssessmentGroups", () => {
  it("shows no fraction, ratio or percentage anywhere", () => {
    // `4 / 4` and `0 / 2 assessed` are readiness scores arrived at sideways (CLAUDE.md
    // §2.6, UI/UX §6.2), and this is the assertion that stops one coming back.
    const { container } = render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    expect(container.textContent).not.toMatch(/%|\d+\s*\/\s*\d+|\d+ of \d+|\d+ out of \d+/);
  });

  it("states what a group's members concluded, in counts of named states", () => {
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    expect(screen.getByText("4 supported")).toBeInTheDocument();
    expect(
      screen.getByText("1 not currently satisfied · 1 near threshold · 3 supported"),
    ).toBeInTheDocument();
  });

  it("never gives a group a verdict of its own", () => {
    // No rule concludes anything about a group. "Residence: not currently satisfied" would
    // be a claim about five requirements on the strength of one — and the counts above
    // already say which of them said what.
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    const residence = screen.getByRole("link", { name: "Residence" }).closest("li");
    expect(residence?.textContent).toMatch(/^Residence1 not currently satisfied/);
  });

  it("states an unassessed group as unassessed, not as a remainder", () => {
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    expect(screen.getByText("2 not yet assessed")).toBeInTheDocument();
  });

  it("links each group to its heading on the Requirements destination", () => {
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    expect(screen.getByRole("link", { name: "Residence" })).toHaveAttribute(
      "href",
      "/cases/c1/requirements#group-RESIDENCE",
    );
  });

  it("offers a way to all requirements, not only to one group", () => {
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    expect(screen.getByRole("link", { name: /View all requirements/ })).toHaveAttribute(
      "href",
      "/cases/c1/requirements",
    );
  });

  it("describes each group link by its state, so focusing it announces how the group stands", () => {
    // Listing links should hear "Residence", not a forty-character sentence; focusing it
    // should still convey the state, which an adjacent span alone would not.
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    const link = screen.getByRole("link", { name: "Residence" });
    const describedBy = link.getAttribute("aria-describedby");
    expect(describedBy).toBe("group-state-RESIDENCE");
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      "1 not currently satisfied · 1 near threshold · 3 supported",
    );
  });

  it("says which group holds stale conclusions, which the case-level signal cannot", () => {
    const groups = canonicalGroups();
    groups[1] = aGroup({ ...groups[1], stale: 5, currency: "STALE" });
    render(<AssessmentGroups overview={anOverview(groups)} />);

    const residence = screen.getByRole("link", { name: "Residence" }).closest("li");
    expect(within(residence!).getByText("5 stale")).toBeInTheDocument();

    // And only that group — a group with current conclusions is not marked.
    const identity = screen.getByRole("link", { name: "Identity and status" }).closest("li");
    expect(within(identity!).queryByText(/stale/)).not.toBeInTheDocument();
  });

  it("uses the singular for one stale conclusion", () => {
    const groups = canonicalGroups();
    groups[1] = aGroup({ ...groups[1], stale: 1, currency: "STALE" });
    render(<AssessmentGroups overview={anOverview(groups)} />);
    expect(screen.getByText("1 stale")).toBeInTheDocument();
  });

  it("renders nothing when the case has no groups", () => {
    const { container } = render(<AssessmentGroups overview={anOverview([])} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("falls back to a humanised key rather than showing a raw enum", () => {
    const groups = [aGroup({ group_key: "SOME_NEW_GROUP" })];
    render(<AssessmentGroups overview={anOverview(groups)} />);
    expect(screen.getByRole("link", { name: "Some new group" })).toBeInTheDocument();
  });

  it("keeps the server's group order rather than sorting by state", () => {
    // Ordering by severity here would make the page reshuffle as conclusions change, and
    // the catalogue's display order is the one the Requirements destination uses.
    render(<AssessmentGroups overview={anOverview(canonicalGroups())} />);
    const labels = screen.getAllByRole("link").map((a) => a.textContent?.trim());
    expect(labels.slice(0, 3)).toEqual([
      "Identity and status",
      "Residence",
      "Knowledge and language",
    ]);
  });
});
