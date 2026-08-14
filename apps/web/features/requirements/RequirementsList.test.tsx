import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { RequirementsList } from "./RequirementsList";

function aRequirement(overrides: Record<string, unknown> = {}) {
  return {
    requirement_key: "residence.total_absences",
    title: "Total absences",
    group_key: "RESIDENCE",
    display_order: 7,
    conclusion: "NEAR_THRESHOLD",
    currency: "CURRENT",
    summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
    summary: {
      code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
      parameters: { days: 439, threshold: 450 },
      text: "439 days outside the UK across your five-year qualifying period, from confirmed travel records, against a threshold of 450. That is close to the standard threshold.",
    },
    stale: null,
    updated_at: "2026-08-14T11:36:00Z",
    ...overrides,
  };
}

const unassessed = aRequirement({
  requirement_key: "referees.first",
  title: "First referee",
  group_key: "REFEREES",
  display_order: 12,
  conclusion: "NOT_YET_ASSESSED",
  currency: null,
  summary_code: null,
  summary: null,
  stale: null,
  updated_at: null,
});

describe("RequirementsList", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("shows a loading state, then the requirements grouped by their group", async () => {
    get.mockResolvedValue({ data: [aRequirement(), unassessed] });
    render(<RequirementsList caseId="c1" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading requirements…");

    expect(await screen.findByText("Residence")).toBeInTheDocument();
    expect(screen.getByText("Referees")).toBeInTheDocument();
    expect(screen.getByText("Total absences")).toBeInTheDocument();
  });

  it("renders the server's plain-language summary rather than deriving its own", async () => {
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" />);
    expect(
      await screen.findByText(/439 days outside the UK across your five-year qualifying period/),
    ).toBeInTheDocument();
  });

  it("shows an unassessed requirement honestly, neither hidden nor failing", async () => {
    get.mockResolvedValue({ data: [aRequirement(), unassessed] });
    render(<RequirementsList caseId="c1" />);

    expect(await screen.findByText("First referee")).toBeInTheDocument();
    expect(screen.getByText("Not yet assessed")).toBeInTheDocument();
    expect(screen.getByText("This requirement hasn’t been assessed yet.")).toBeInTheDocument();
    // Not dressed up as a failure...
    expect(screen.queryByText("Not currently satisfied")).not.toBeInTheDocument();
    // ...and not given a currency it does not have.
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
  });

  it("keeps a stale result's conclusion and explains the staleness separately", async () => {
    get.mockResolvedValue({
      data: [
        aRequirement({
          currency: "STALE",
          stale: {
            reason_code: "TRAVEL_RECORD_CHANGED",
            reason: "Your travel records changed after this was worked out.",
            marked_stale_at: "2026-08-14T11:36:00Z",
          },
        }),
      ],
    });
    render(<RequirementsList caseId="c1" />);

    // Conclusion preserved, currency shown separately, reason spelled out.
    expect(await screen.findByText("Near threshold")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(
      screen.getByText(/Your travel records changed after this was worked out/),
    ).toBeInTheDocument();
    // The figure it concluded is still shown — a stale result is not withdrawn.
    expect(screen.getByText(/439 days outside the UK/)).toBeInTheDocument();
  });

  it("offers to run an assessment when nothing has been assessed yet", async () => {
    get.mockResolvedValue({ data: [unassessed] });
    render(<RequirementsList caseId="c1" />);

    expect(await screen.findByText(/Nothing has been assessed yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run assessment" })).toBeInTheDocument();
    // No group listing at all while there is nothing to report.
    expect(screen.queryByText("Referees")).not.toBeInTheDocument();
  });

  it("shows an error state with a retry that refetches", async () => {
    get.mockResolvedValueOnce({ error: { detail: "boom" } });
    render(<RequirementsList caseId="c1" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn’t load the requirements for this case.");

    get.mockResolvedValueOnce({ data: [aRequirement()] });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Total absences")).toBeInTheDocument());
  });

  it("replaces the list with the recalculated results", async () => {
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" />);
    await screen.findByText("Total absences");

    post.mockResolvedValue({
      data: {
        assessment_run_id: "r1",
        mode: "TRUSTED",
        trigger_type: "USER_REQUESTED",
        result_count: 1,
        requirements: [
          aRequirement({
            summary: {
              code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
              parameters: { days: 440, threshold: 450 },
              text: "440 days outside the UK across your five-year qualifying period, from confirmed travel records, against a threshold of 450. That is close to the standard threshold.",
            },
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    await waitFor(() => expect(screen.getByText(/440 days outside the UK/)).toBeInTheDocument());
  });

  it("reports a failed recalculation without changing what is shown", async () => {
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" />);
    await screen.findByText("Total absences");

    post.mockResolvedValue({ error: { detail: "boom" } });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Nothing has changed");
    // The previous conclusion is untouched — a failed run never replaces a result.
    expect(screen.getByText(/439 days outside the UK/)).toBeInTheDocument();
  });

  it("shows no percentage, score or fraction anywhere", async () => {
    get.mockResolvedValue({ data: [aRequirement(), unassessed] });
    const { container } = render(<RequirementsList caseId="c1" />);
    await screen.findByText("Total absences");

    // CLAUDE.md §2.6: no overall readiness score, ever. Guards against a well-meaning
    // "1 of 2 supported" creeping into a group heading.
    expect(container.textContent).not.toMatch(/%/);
    expect(container.textContent).not.toMatch(/\b\d+\s*(of|\/)\s*\d+\b/);
  });
});
