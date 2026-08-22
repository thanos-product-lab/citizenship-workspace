"use client";

import type { Timeline, TimelineTrip } from "./useTimeline";

/**
 * The five-year residence picture as a shape.
 *
 * **Decoration over the table, and nothing more.** It is `aria-hidden`, it introduces no
 * fact the table does not already carry, and the table is never hidden or collapsed to
 * make room for it. UI/UX §15 asks for a visualisation *and* a semantically equivalent
 * table; building the table first (slice 4) is what makes "equivalent" checkable, and this
 * has to earn its place against something already complete rather than the other way round.
 *
 * What the shape adds that a list cannot: twelve trips over 1,826 days read as a rhythm —
 * clustered, sparse, longer at one end — and the two facts the whole case turns on land
 * where they belong in that rhythm. The window's first day is at the very left edge, and a
 * bar sitting on it is why the canonical case fails presence.
 *
 * **No charting library.** A linear date→x scale over a fixed five-year domain is the
 * arithmetic below; D3 would be a dependency and a build-size cost to replace nine lines
 * (CLAUDE.md §10 and the roadmap's "do not add dependencies without asking").
 *
 * **No SVG text.** Labels are real DOM outside the drawing, so they inherit the page's
 * font scaling and reflow instead of scaling with the viewBox — SVG text at 200% zoom
 * shrinks relative to everything around it, which is the usual way a chart quietly breaks
 * the zoom requirement.
 */

const VIEW_WIDTH = 1000;
const VIEW_HEIGHT = 96;
const BASELINE_Y = 66;
const BAR_HEIGHT = 22;
/** A five-day trip over five years is 2.7px wide. Below this it is invisible. */
const MIN_BAR_WIDTH = 3;
/**
 * How much taller the trip covering the presence anchor is drawn.
 *
 * The anchor is the window's first day by construction, so it is always the left edge, and
 * a trip covering it is always a sliver pinned against that edge — the most consequential
 * mark on the drawing and the easiest to lose. Height is the signal because it survives
 * greyscale: an outline alone made it indistinguishable from the boundary line beside it.
 */
const ANCHOR_BAR_RISE = 10;

/**
 * ISO date → day number, via `Date.UTC` so no local timezone can shift it across a
 * boundary. This is presentation arithmetic — a pixel position — not a domain calculation:
 * every day count on this screen is computed server-side and passed through (CLAUDE.md §8).
 */
function dayNumber(iso: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return Number.NaN;
  const [, y, m, d] = match;
  return Date.UTC(Number(y), Number(m) - 1, Number(d)) / 86_400_000;
}

export function TimelineBand({ timeline }: { timeline: Timeline }) {
  const start = dayNumber(timeline.qualifying_period_start);
  const end = dayNumber(timeline.qualifying_period_end);
  const span = end - start;
  if (!Number.isFinite(span) || span <= 0) return null;

  const x = (iso: string): number => ((dayNumber(iso) - start) / span) * VIEW_WIDTH;
  const clamp = (value: number): number => Math.min(VIEW_WIDTH, Math.max(0, value));

  // Only trips with days inside the window are drawn. Ones wholly outside would either
  // stretch the axis until five years became a sliver, or sit off the edge — and they are
  // in the table, marked and explained, which is where a fact that changes no figure
  // belongs.
  const drawn = timeline.trips.filter((trip) => !trip.is_outside_window);
  const finalYearX = clamp(x(timeline.final_year_start));

  return (
    <figure className="cw-band">
      <svg
        className="cw-band__svg"
        viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
        preserveAspectRatio="none"
        // Decoration. Every value drawn here is in the table below, described in words.
        // A screen reader that announced this would be reading a second, worse copy.
        aria-hidden="true"
        focusable="false"
      >
        {/* The final twelve months, shaded. It has its own threshold (90 days) and its own
            requirement, so it is a region rather than a line. */}
        <rect
          x={finalYearX}
          y={BASELINE_Y - BAR_HEIGHT - ANCHOR_BAR_RISE - 6}
          width={VIEW_WIDTH - finalYearX}
          height={BAR_HEIGHT + ANCHOR_BAR_RISE + 18}
          className="cw-band__final-year"
        />

        {yearTicks(timeline).map((tick) => (
          <line
            key={tick.iso}
            x1={clamp(x(tick.iso))}
            x2={clamp(x(tick.iso))}
            y1={BASELINE_Y - BAR_HEIGHT - ANCHOR_BAR_RISE - 6}
            y2={BASELINE_Y + 6}
            className="cw-band__tick"
          />
        ))}

        {/* The UK baseline: the default state the bars are absences from. */}
        <line
          x1={0}
          x2={VIEW_WIDTH}
          y1={BASELINE_Y}
          y2={BASELINE_Y}
          className="cw-band__baseline"
        />

        {drawn.map((trip) => (
          <TripBar key={trip.travel_record_id} trip={trip} x={x} clamp={clamp} />
        ))}

        {/* The first day of the qualifying period — the single day presence is tested on,
            and by construction the left edge. Drawn full height so it reads as a boundary
            of the whole picture rather than a mark on the baseline. */}
        <line
          x1={1}
          x2={1}
          y1={4}
          y2={BASELINE_Y + 12}
          className={
            timeline.presence_anchor_is_absent
              ? "cw-band__anchor cw-band__anchor--absent"
              : "cw-band__anchor"
          }
        />
      </svg>

      {/* Real DOM, outside the drawing: these scale with the page rather than the viewBox. */}
      <div className="cw-band__axis">
        {yearTicks(timeline).map((tick) => (
          <span
            key={tick.iso}
            className="cw-band__axis-label"
            style={{ left: `${(clamp(x(tick.iso)) / VIEW_WIDTH) * 100}%` }}
          >
            {tick.label}
          </span>
        ))}
      </div>

      <figcaption className="cw-band__caption">
        Your qualifying period, earliest on the left. Each bar is a trip; the shaded region
        is the final twelve months. The marked left edge is the first day of the period —
        the one day presence is tested on. Every figure is in the table below.
      </figcaption>
    </figure>
  );
}

function TripBar({
  trip,
  x,
  clamp,
}: {
  trip: TimelineTrip;
  x: (iso: string) => number;
  clamp: (value: number) => number;
}) {
  const left = clamp(x(trip.departure_date));
  const right = clamp(x(trip.return_date));
  const width = Math.max(MIN_BAR_WIDTH, right - left);
  const rise = trip.covers_presence_anchor ? ANCHOR_BAR_RISE : 0;
  const classes = ["cw-band__trip"];
  if (!trip.is_trusted) classes.push("cw-band__trip--unconfirmed");
  if (trip.covers_presence_anchor) classes.push("cw-band__trip--anchor");

  return (
    <rect
      // Clipped at the window edges rather than drawn past them: a bar extending beyond
      // the axis would suggest days that count, and they do not.
      x={left}
      y={BASELINE_Y - BAR_HEIGHT - rise}
      width={Math.min(width, VIEW_WIDTH - left)}
      height={BAR_HEIGHT + rise}
      rx={2}
      className={classes.join(" ")}
    />
  );
}

/** The 1 January inside the window, one per year, for the axis. */
function yearTicks(timeline: Timeline): { iso: string; label: string }[] {
  const first = Number(timeline.qualifying_period_start.slice(0, 4));
  const last = Number(timeline.qualifying_period_end.slice(0, 4));
  if (!Number.isFinite(first) || !Number.isFinite(last)) return [];
  const ticks: { iso: string; label: string }[] = [];
  for (let year = first + 1; year <= last; year += 1) {
    ticks.push({ iso: `${year}-01-01`, label: String(year) });
  }
  return ticks;
}
