import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithQuery as render } from "@/test/render";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

  it("offers the first assessment from the empty state, and reports it failing", async () => {
    // The one recalculation control this list owns: the header's Recalculate is hidden
    // until something has been assessed, so before the first run this is the only way in.
    get.mockResolvedValue({ data: [aRequirement({ conclusion: "NOT_YET_ASSESSED", currency: null })] });
    render(<RequirementsList caseId="c1" />);
    // With nothing assessed the list shows its empty state rather than the rows.
    const run = await screen.findByRole("button", { name: "Run assessment" });

    post.mockResolvedValue({ error: { detail: "boom" } });
    fireEvent.click(run);

    const alert = await screen.findByRole("alert");
    // Not "nothing has changed": a timeout or a dropped response after commit would make
    // that false, and the user would be told the case is unchanged while looking at a
    // list that is out of date.
    expect(alert).toHaveTextContent("couldn’t confirm whether that recalculation ran");
  });

  describe("group deep links from the Overview", () => {
    // jsdom implements no layout and so has no real scrollIntoView (test/setup.ts stubs
    // it). Spying here makes the scroll observable.
    const scrollIntoView = vi.spyOn(Element.prototype, "scrollIntoView");

    afterEach(() => {
      window.location.hash = "";
      scrollIntoView.mockClear();
    });

    it("resolves #group-<key> after the data arrives, not at navigation time", async () => {
      // The browser resolves a fragment when the page loads, at which point this list has
      // not fetched and the heading does not exist — so the jump silently does nothing and
      // the reader lands at the top of a long page instead of at the group they chose.
      window.location.hash = "#group-RESIDENCE";
      get.mockResolvedValue({ data: [aRequirement()] });
      render(<RequirementsList caseId="c1" />);

      const heading = await screen.findByRole("heading", { name: "Residence" });
      // Focus, so the deep link means the same thing to a keyboard or screen-reader user
      // as it does to a sighted one.
      await waitFor(() => expect(heading).toHaveFocus());
      expect(heading).toHaveAttribute("tabindex", "-1");

      // And the scroll, which is what a sighted user actually sees. Asserted separately
      // because an earlier version moved focus and failed to scroll — the animated scroll
      // was cancelled before it arrived — and a focus-only assertion called that a pass.
      // jsdom has no layout, so the call itself is the observable behaviour; `instant` is
      // part of it, since that is what stops the scroll being cancelled.
      expect(scrollIntoView).toHaveBeenCalledWith({ block: "start", behavior: "instant" });
      expect(scrollIntoView.mock.instances[0]).toBe(heading);
    });

    it("leaves the page alone when there is no group fragment", async () => {
      get.mockResolvedValue({ data: [aRequirement()] });
      render(<RequirementsList caseId="c1" />);
      const heading = await screen.findByRole("heading", { name: "Residence" });
      expect(heading).not.toHaveFocus();
      expect(heading).not.toHaveAttribute("tabindex");
      expect(scrollIntoView).not.toHaveBeenCalled();
    });

    it("ignores a fragment naming a group this case does not have", async () => {
      window.location.hash = "#group-NOT_A_GROUP";
      get.mockResolvedValue({ data: [aRequirement()] });
      render(<RequirementsList caseId="c1" />);
      const heading = await screen.findByRole("heading", { name: "Residence" });
      expect(heading).not.toHaveFocus();
      expect(scrollIntoView).not.toHaveBeenCalled();
    });

    it("ignores a fragment that is not a group at all", async () => {
      window.location.hash = "#something-else";
      get.mockResolvedValue({ data: [aRequirement()] });
      render(<RequirementsList caseId="c1" />);
      const heading = await screen.findByRole("heading", { name: "Residence" });
      expect(heading).not.toHaveFocus();
      expect(scrollIntoView).not.toHaveBeenCalled();
    });
  });

  it("leaves Recalculate to the case header", () => {
    // It is a case-level command — a new AssessmentRun for every requirement, not only the
    // ones on this destination — so it belongs to the case, not to this page.
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" />);
    expect(screen.queryByRole("button", { name: "Recalculate" })).not.toBeInTheDocument();
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

  it("refetches when the case's queries are invalidated", async () => {
    get.mockResolvedValue({ data: [aRequirement()] });
    const { client } = render(<RequirementsList caseId="c1" />);
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
    await client.invalidateQueries({ queryKey: ["cases", "c1"] });
    await waitFor(() => expect(screen.getByText("Stale")).toBeInTheDocument());
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

  it("marks a group heading stale when the summary says a member is", async () => {
    // R5: GroupHeadingSummary was only ever exercised in its fallback shape, so the stale
    // marker — the entire reason ADR-0010 surfaces at group level — had no test.
    get.mockResolvedValue({ data: [aRequirement()] });
    render(
      <RequirementsList
        caseId="c1"
        groupSummaries={[
          {
            group_key: "RESIDENCE",
            conclusion_counts: [{ conclusion: "SUPPORTED", count: 5 }],
            not_yet_assessed: 0,
            total: 5,
            currency: "STALE",
            needs_attention: 0,
            stale: 2,
            is_fully_concluded: true,
            requirements: [],
          },
        ]}
      />,
    );
    await screen.findByText("Total absences");
    expect(screen.getByText("2 conclusions are stale")).toBeInTheDocument();
  });

  it("falls back to a count-only heading when no summary is available", async () => {
    // A failed overview fetch must not leave the heading asserting a shape sourced from a
    // different payload — count only, no stale marker either way.
    get.mockResolvedValue({ data: [aRequirement()] });
    render(<RequirementsList caseId="c1" groupSummaries={[]} />);
    await screen.findByText("Total absences");
    expect(screen.getByText("1 requirement")).toBeInTheDocument();
    expect(screen.queryByText(/conclusions are stale/)).not.toBeInTheDocument();
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
