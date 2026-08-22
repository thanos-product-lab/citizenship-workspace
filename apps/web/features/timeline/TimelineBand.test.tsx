import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";

import { describe, expect, it } from "vitest";

import { TimelineBand } from "./TimelineBand";
import type { Timeline } from "./useTimeline";

function aTrip(overrides: Partial<Timeline["trips"][number]> = {}) {
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
  } as Timeline["trips"][number];
}

function aTimeline(overrides: Partial<Timeline> = {}): Timeline {
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
  } as Timeline;
}

function bars(container: HTMLElement): SVGRectElement[] {
  return Array.from(container.querySelectorAll<SVGRectElement>(".cw-band__trip"));
}

describe("TimelineBand", () => {
  it("is hidden from assistive technology", () => {
    // Every value it draws is in the table below, in words. A screen reader announcing
    // this would be reading a second, worse copy of the same facts.
    const { container } = render(<TimelineBand timeline={aTimeline()} />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("focusable", "false");
    // Nothing inside it is reachable by keyboard either.
    expect(container.querySelectorAll("svg a, svg button, svg [tabindex]")).toHaveLength(0);
  });

  it("says in visible text what it is showing", () => {
    // The caption is real DOM, not SVG text: it has to be readable by everyone and to
    // scale with the page rather than the viewBox.
    render(<TimelineBand timeline={aTimeline()} />);
    expect(screen.getByText(/each bar is a trip/i)).toBeInTheDocument();
    expect(screen.getByText(/every figure is in the table below/i)).toBeInTheDocument();
  });

  it("places a trip proportionally within the five-year window", () => {
    const { container } = render(
      <TimelineBand
        timeline={aTimeline({
          trips: [
            aTrip({ travel_record_id: "mid", departure_date: "2024-10-15", return_date: "2024-10-25", covers_presence_anchor: false }),
          ],
        })}
      />,
    );
    // 2024-10-15 is a little over halfway through 16 Apr 2022 – 15 Apr 2027.
    const bar = bars(container)[0]!;
    const x = Number(bar.getAttribute("x"));
    expect(x).toBeGreaterThan(480);
    expect(x).toBeLessThan(520);
  });

  it("gives a short trip a visible width rather than a sliver", () => {
    // A two-day trip over 1,826 days is 1.1px at the drawing's own scale, and a bar the
    // user cannot see is the same as a trip that is not there.
    //
    // The fixture is two days on purpose. An earlier version used six, which is already
    // 3.3px wide — so the clamp never engaged and removing it left this test green.
    const { container } = render(
      <TimelineBand
        timeline={aTimeline({
          trips: [
            aTrip({
              departure_date: "2026-05-04",
              return_date: "2026-05-06",
              covers_presence_anchor: false,
            }),
          ],
        })}
      />,
    );
    const width = Number(bars(container)[0]!.getAttribute("width"));
    expect(width).toBeGreaterThanOrEqual(3);
    // And the clamp is what did it, not the arithmetic.
    expect(width).toBeGreaterThan((2 / 1825) * 1000);
  });

  it("does not draw a trip that falls outside the window", () => {
    // Drawing it would either stretch the axis until five years became a sliver, or put a
    // bar past the edge implying days that count. The table lists it, marked.
    const { container } = render(
      <TimelineBand
        timeline={aTimeline({
          trips: [
            aTrip({ travel_record_id: "old", is_outside_window: true, covers_presence_anchor: false }),
            aTrip({ travel_record_id: "in" }),
          ],
        })}
      />,
    );
    expect(bars(container)).toHaveLength(1);
  });

  it("clips a trip that straddles the start rather than drawing past the edge", () => {
    const { container } = render(<TimelineBand timeline={aTimeline()} />);
    // The canonical first trip departs 14 April, two days before the window opens.
    const bar = bars(container)[0]!;
    expect(Number(bar.getAttribute("x"))).toBe(0);
  });

  it("marks the trip covering the day presence is tested on", () => {
    const { container } = render(<TimelineBand timeline={aTimeline()} />);
    const bar = bars(container)[0]!;
    expect(bar).toHaveClass("cw-band__trip--anchor");
    expect(container.querySelector(".cw-band__anchor--absent")).toBeInTheDocument();
    // Drawn taller than its neighbours, not merely outlined. Against the boundary line it
    // is always a sliver pinned to the left edge, and an outline alone made the two
    // indistinguishable — height is the signal that survives greyscale.
    const plain = render(
      <TimelineBand
        timeline={aTimeline({ trips: [aTrip({ covers_presence_anchor: false })] })}
      />,
    );
    const plainBar = plain.container.querySelector<SVGRectElement>(".cw-band__trip")!;
    expect(Number(bar.getAttribute("height"))).toBeGreaterThan(
      Number(plainBar.getAttribute("height")),
    );
  });

  it("distinguishes an unconfirmed trip by texture, not by hue alone", () => {
    const { container } = render(
      <TimelineBand
        timeline={aTimeline({ trips: [aTrip({ is_trusted: false, covers_presence_anchor: false })] })}
      />,
    );
    expect(bars(container)[0]).toHaveClass("cw-band__trip--unconfirmed");
  });

  it("names the three things the drawing marks", () => {
    // Without these the shape has to be decoded from the caption, and the shaded region
    // in particular is unreadable as "the final twelve months" unless something says so
    // beside it.
    render(<TimelineBand timeline={aTimeline()} />);
    expect(screen.getByText("First day tested")).toBeInTheDocument();
    expect(screen.getByText("Final 12 months")).toBeInTheDocument();
    expect(screen.getByText("Application date")).toBeInTheDocument();
  });

  it("labels each year on the axis", () => {
    render(<TimelineBand timeline={aTimeline()} />);
    for (const year of ["2023", "2024", "2025", "2026", "2027"]) {
      expect(screen.getByText(year)).toBeInTheDocument();
    }
    // Not 2022: the window opens in April, so a 1 January tick would sit off the left edge.
    expect(screen.queryByText("2022")).not.toBeInTheDocument();
  });

  it("renders nothing rather than something wrong when the window is unusable", () => {
    const { container } = render(
      <TimelineBand
        timeline={aTimeline({
          qualifying_period_start: "2027-04-15",
          qualifying_period_end: "2027-04-15",
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
