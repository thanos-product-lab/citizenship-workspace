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
    // The visible text carries no role: the announcement is made by the persistent
    // aria-live region, and a second role="status" here would announce it twice.
    expect(screen.getByText("Loading requirements…")).toBeInTheDocument();

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

  it("tells the parent a recalculation landed, so the derived phase can refresh", async () => {
    // Caught in the browser, not by a test: after "Run assessment" the phase pill still
    // read "Setting up" beside a fully assessed list. The phase is derived from
    // assessment state (ADR-0009), so the case has to be refetched when a run lands.
    const onAssessmentRun = vi.fn();
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" onAssessmentRun={onAssessmentRun} />);
    await screen.findByText("Total absences");

    post.mockResolvedValue({
      data: {
        assessment_run_id: "r1",
        mode: "TRUSTED",
        trigger_type: "USER_REQUESTED",
        result_count: 1,
        requirements: [aRequirement()],
      },
    });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    await waitFor(() => expect(onAssessmentRun).toHaveBeenCalledTimes(1));
  });

  it("does not claim a recalculation landed when it failed", async () => {
    const onAssessmentRun = vi.fn();
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" onAssessmentRun={onAssessmentRun} />);
    await screen.findByText("Total absences");

    post.mockResolvedValue({ error: { detail: "boom" } });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));
    await screen.findByRole("alert");
    expect(onAssessmentRun).not.toHaveBeenCalled();
  });

  it("reports a failed recalculation without changing what is shown", async () => {
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" />);
    await screen.findByText("Total absences");

    post.mockResolvedValue({ error: { detail: "boom" } });
    fireEvent.click(screen.getByRole("button", { name: "Recalculate" }));

    const alert = await screen.findByRole("alert");
    // Not "nothing has changed": a timeout or a dropped response after commit would make
    // that false, and the user would be told the case is unchanged while looking at a
    // list that is out of date.
    expect(alert).toHaveTextContent("couldn’t confirm whether that recalculation ran");
    // The previous conclusion is untouched — a failed run never replaces a result.
    expect(screen.getByText(/439 days outside the UK/)).toBeInTheDocument();
  });

  it("never claims a stale conclusion still stands", async () => {
    // The one claim the system cannot make. A STALE result means the inputs beneath the
    // conclusion changed and it has NOT been re-evaluated — the canonical demo case
    // exists to show 439 -> 440 crossing a band. Saying "this conclusion still stands"
    // would collapse currency into conclusion by prose rather than by enum.
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
    const { container } = render(<RequirementsList caseId="c1" />);
    await screen.findByText("Total absences");

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/still stands/i);
    expect(text).not.toMatch(/still (valid|holds|applies|accurate)/i);
    expect(text).toMatch(/has not been rechecked/i);
  });

  it("refetches when the parent signals a residence input changed", async () => {
    // Travel and application-date writes mark residence results STALE server-side in the
    // same transaction. Those inputs sit directly above this list on the same page, so
    // without a refetch the user keeps looking at conclusions the API has already flagged.
    get.mockResolvedValue({ data: [aRequirement()] });
    const { rerender } = render(<RequirementsList caseId="c1" refreshToken={0} />);
    await screen.findByText("Total absences");
    expect(get).toHaveBeenCalledTimes(1);

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
    rerender(<RequirementsList caseId="c1" refreshToken={1} />);
    await waitFor(() => expect(screen.getByText("Stale")).toBeInTheDocument());
    expect(get).toHaveBeenCalledTimes(2);
  });

  it("still lists a stored NOT_YET_ASSESSED result that has a currency", async () => {
    // A placeholder result (the route rules emit these) is a real result with a real
    // currency. Filtering the list on the conclusion would hide it — including when the
    // thing being hidden is STALE.
    get.mockResolvedValue({
      data: [
        aRequirement({
          requirement_key: "route.adult_applicant",
          title: "Adult applicant",
          group_key: "ROUTE_AND_STATUS",
          display_order: 1,
          conclusion: "NOT_YET_ASSESSED",
          currency: "CURRENT",
          summary_code: null,
          summary: null,
        }),
      ],
    });
    render(<RequirementsList caseId="c1" />);
    expect(await screen.findByText("Adult applicant")).toBeInTheDocument();
    expect(screen.queryByText(/Nothing has been assessed yet/)).not.toBeInTheDocument();
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
