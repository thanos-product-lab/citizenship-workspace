import "@testing-library/jest-dom/vitest";

import { screen, waitFor, within } from "@testing-library/react";

import { renderWithQuery as render } from "@/test/render";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const client = { GET: get, POST: vi.fn(), PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { ResidenceTimeline } from "./ResidenceTimeline";

function aTrip(overrides: Record<string, unknown> = {}) {
  return {
    travel_record_id: "t1",
    destination_label: "Spain",
    departure_date: "2022-04-14",
    return_date: "2022-04-26",
    date_confidence: "EXACT",
    review_state: "CONFIRMED",
    is_trusted: true,
    absent_days: 11,
    counted_days: 10,
    is_outside_window: false,
    covers_presence_anchor: true,
    overlaps_with: [],
    ...overrides,
  };
}

/** The canonical case's shape: window from 15 April 2027, trip 1 covering the anchor. */
function aTimeline(overrides: Record<string, unknown> = {}) {
  return {
    application_date: "2027-04-15",
    qualifying_period_start: "2022-04-16",
    qualifying_period_end: "2027-04-15",
    final_year_start: "2026-04-16",
    final_year_end: "2027-04-15",
    presence_anchor: "2022-04-16",
    presence_anchor_is_absent: true,
    assessment_is_stale: false,
    totals: {
      qualifying_period_days: 439,
      final_year_days: 17,
      qualifying_period_days_including_unconfirmed: 439,
      final_year_days_including_unconfirmed: 17,
      trip_count: 12,
      unconfirmed_trip_count: 0,
    },
    trips: [aTrip()],
    ...overrides,
  };
}

describe("ResidenceTimeline", () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: aTimeline(), error: undefined });
  });

  it("states the period being measured, including the day presence is tested on", async () => {
    const { container } = render(<ResidenceTimeline caseId="c1" />);

    expect(await screen.findByText("16 April 2022 to 15 April 2027")).toBeInTheDocument();
    // Scoped to the boundaries list: "First day tested" appears twice on the page, here
    // and as the band's own label for the same edge. That duplication is deliberate — one
    // term for one concept — so the query names which of the two it means.
    const boundaries = within(container.querySelector(".cw-timeline__boundaries")!);
    // The anchor is one date out of eighteen hundred and it decides the presence check,
    // so it is named rather than left for the reader to derive from the window.
    //
    // The *term* carries "this is the day presence is decided on"; the value carries the
    // fact. A sentence restating the label is a sentence doing the label's job.
    const anchor = boundaries.getByText("First day tested").closest("div");
    expect(anchor).toHaveTextContent("16 April 2022");
    expect(anchor).toHaveTextContent(/you were outside the UK on this day/i);
  });

  it("is a real table with its columns and rows named", async () => {
    render(<ResidenceTimeline caseId="c1" />);

    const table = await screen.findByRole("table", { name: /your trips, earliest first/i });
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((cell) => cell.textContent);
    // Three columns. Departure and return are one fact, and a "Record" column reading
    // "Confirmed" on every row buried the one row that was not.
    expect(headers).toEqual(["Destination", "Trip dates", "Days counted"]);
    expect(within(table).getAllByRole("rowgroup")).toHaveLength(3);
  });

  it("carries the table roles explicitly, not only implicitly", async () => {
    // Below 34rem the stylesheet sets `display: block` so the columns can stack, and that
    // strips the implicit table semantics from every element. The explicit roles are what
    // survive it.
    //
    // Asserted as attributes rather than through `getByRole`, deliberately. jsdom applies
    // no CSS, so the reflow never happens and the implicit roles are always present —
    // deleting every `role=` from this component leaves a role-based assertion completely
    // green, which is what happened when this test was first written. The attribute check
    // is a weaker claim than "the semantics survive the reflow", but it is the claim this
    // environment can actually make, and it catches the deletion.
    const { container } = render(<ResidenceTimeline caseId="c1" />);
    const table = await screen.findByRole("table");

    expect(table).toHaveAttribute("role", "table");
    expect(container.querySelectorAll('[role="rowgroup"]')).toHaveLength(3);
    expect(container.querySelectorAll('[role="columnheader"]')).toHaveLength(3);
    expect(container.querySelectorAll('[role="rowheader"]')).toHaveLength(1);
    expect(container.querySelectorAll('[role="row"]').length).toBeGreaterThanOrEqual(3);
    expect(container.querySelectorAll('[role="cell"]').length).toBeGreaterThanOrEqual(3);
  });

  it("explains why a trip's counted days differ from its length", async () => {
    render(<ResidenceTimeline caseId="c1" />);

    const row = (await screen.findByText("Spain")).closest("tr")!;
    expect(within(row).getByText("10 days")).toBeInTheDocument();
    // The single most common reason a user's own arithmetic disagrees with ours.
    expect(row).toHaveTextContent(/out of 11 days away/i);
    expect(row).toHaveTextContent(/days you left and returned are UK days and never count/i);
    expect(row).toHaveTextContent(/1 day of this trip falls outside your qualifying period/i);
    expect(row).toHaveTextContent(/so 10 days count\./i);
  });

  it("flags the trip that covers the day presence is tested on", async () => {
    render(<ResidenceTimeline caseId="c1" />);

    const row = (await screen.findByText("Spain")).closest("tr")!;
    expect(row).toHaveTextContent(/covers the first day tested/i);
  });

  it("keeps an out-of-window trip and says in words why it counts for nothing", async () => {
    get.mockResolvedValue({
      data: aTimeline({
        trips: [
          aTrip({
            travel_record_id: "t2",
            destination_label: "Long ago",
            counted_days: 0,
            absent_days: 30,
            is_outside_window: true,
            covers_presence_anchor: false,
          }),
        ],
      }),
      error: undefined,
    });
    render(<ResidenceTimeline caseId="c1" />);

    const row = (await screen.findByText("Long ago")).closest("tr")!;
    // Recessed visually, but the reason is in text — the row must not depend on being
    // greyer than its neighbours to be understood.
    expect(row).toHaveTextContent(/falls entirely outside your qualifying period/i);
    expect(row).toHaveTextContent(/kept for your records/i);
  });

  it("labels only the unconfirmed record, never the ordinary state", async () => {
    // Twelve rows reading "Confirmed" is twelve repetitions of the unremarkable, and it
    // buries the one row that is not. The travel table set this convention first.
    render(<ResidenceTimeline caseId="c1" />);
    await screen.findByRole("table");
    expect(screen.queryByText("Confirmed")).not.toBeInTheDocument();
    // And the flag is not the new noise: every record here is confirmed, so no row
    // carries the exception badge either. Asserting only the absence of "Confirmed" left
    // "flag every row as unconfirmed" green, which is the same defect wearing a different
    // word.
    expect(screen.queryByText("Not confirmed")).not.toBeInTheDocument();
    expect(screen.queryByText(/left out of your confirmed totals/i)).not.toBeInTheDocument();
  });

  it("gives a trip's dates as one fact rather than two columns", async () => {
    render(<ResidenceTimeline caseId="c1" />);
    const row = (await screen.findByText("Spain")).closest("tr")!;
    expect(within(row).getByText("14 April 2022 to 26 April 2022")).toBeInTheDocument();
  });

  it("distinguishes an unconfirmed record without relying on colour", async () => {
    get.mockResolvedValue({
      data: aTimeline({
        totals: { ...aTimeline().totals, unconfirmed_trip_count: 1,
          qualifying_period_days_including_unconfirmed: 469 },
        trips: [aTrip({ is_trusted: false, date_confidence: "ESTIMATED" })],
      }),
      error: undefined,
    });
    render(<ResidenceTimeline caseId="c1" />);

    const row = (await screen.findByText("Spain")).closest("tr")!;
    expect(within(row).getByText("Not confirmed")).toBeInTheDocument();
    expect(row).toHaveTextContent(/left out of your confirmed totals/i);
    // And the totals say what leaving it out costs, rather than silently excluding it.
    expect(screen.getByText(/left out of those totals/i)).toBeInTheDocument();
    expect(screen.getByText(/counting them would give 469 days/i)).toBeInTheDocument();
  });

  it("names an overlap without implying it inflated a total", async () => {
    get.mockResolvedValue({
      data: aTimeline({ trips: [aTrip({ overlaps_with: ["t9"] })] }),
      error: undefined,
    });
    render(<ResidenceTimeline caseId="c1" />);

    const row = (await screen.findByText("Spain")).closest("tr")!;
    expect(row).toHaveTextContent(/overlap is counted once/i);
    expect(row).toHaveTextContent(/one of the two records is likely wrong/i);
  });

  it("says when the conclusions are behind the records", async () => {
    get.mockResolvedValue({ data: aTimeline({ assessment_is_stale: true }), error: undefined });
    render(<ResidenceTimeline caseId="c1" />);

    expect(await screen.findByText(/conclusions were reached before your latest change/i))
      .toBeInTheDocument();
  });

  it("does not show a conclusion or a currency anywhere", async () => {
    get.mockResolvedValue({
      data: aTimeline({ assessment_is_stale: true, trips: [aTrip({ is_trusted: false })] }),
      error: undefined,
    });
    const { container } = render(<ResidenceTimeline caseId="c1" />);
    await screen.findByRole("table");

    // Conclusions belong to AssessmentResult and live on Requirements (ADR-0007). A
    // second surface publishing its own would be a second answer to one question.
    for (const word of ["Supported", "Near threshold", "Not currently satisfied", "Current"]) {
      expect(container).not.toHaveTextContent(word);
    }
  });

  it("explains the totals row rather than leaving a bare figure", async () => {
    render(<ResidenceTimeline caseId="c1" />);

    const table = await screen.findByRole("table");
    const total = within(table).getByRole("rowheader", { name: /total counted/i }).closest("tr")!;
    expect(within(total).getByText("439 days")).toBeInTheDocument();
    expect(total).toHaveTextContent(/union of your confirmed trips/i);
    expect(total).toHaveTextContent(/overlapping days are counted once/i);
  });

  it("sends the user to choose a date rather than showing an empty window", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    render(<ResidenceTimeline caseId="c1" />);

    expect(await screen.findByRole("link", { name: /choose an application date/i }))
      .toHaveAttribute("href", "/cases/c1/data");
  });

  it("offers a retry when the timeline cannot be loaded", async () => {
    get.mockResolvedValue({ data: undefined, error: {} });
    render(<ResidenceTimeline caseId="c1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn’t load your timeline/i);
    get.mockResolvedValue({ data: aTimeline(), error: undefined });
    (await screen.findByRole("button", { name: /try again/i })).click();
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
  });

  it("says what zero trips means rather than showing an empty table", async () => {
    get.mockResolvedValue({
      data: aTimeline({ trips: [], totals: { ...aTimeline().totals, trip_count: 0 } }),
      error: undefined,
    });
    render(<ResidenceTimeline caseId="c1" />);

    expect(await screen.findByText(/haven’t recorded any trips/i)).toBeInTheDocument();
    expect(screen.getByText(/your absence totals are zero/i)).toBeInTheDocument();
  });
});
