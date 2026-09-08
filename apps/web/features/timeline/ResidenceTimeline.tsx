"use client";

import { formatDate } from "@/features/requirements/dates";

import { TimelineBand } from "./TimelineBand";
import { StatusBadge, cardStyle, errorTextStyle, buttonStyle } from "@/components/ui";
import { type Timeline, type TimelineTrip, useTimeline } from "./useTimeline";

/**
 * The residence timeline as a chronological table.
 *
 * **The table is the artifact, not the fallback.** UI/UX §15 asks for the visualisation and
 * a semantically equivalent table; building the table first is what makes "equivalent"
 * checkable rather than aspirational, because the visual band that follows has to earn its
 * place against something already complete. Everything a sighted user will read off the
 * chart is here in text, and nothing here is only in the chart.
 *
 * Three things this screen has to say that a list of dates cannot:
 *
 * - **Which days actually count.** A trip's length and its contribution differ whenever it
 *   straddles a window boundary — the first trip is abroad eleven days and contributes
 *   ten — so both figures are shown and the difference is spelled out rather than left as
 *   arithmetic the user gets wrong and distrusts.
 * - **Which single day decides presence.** The anchor is one date out of eighteen hundred,
 *   and the trip covering it is why the canonical case fails. It is named in the
 *   boundaries list and flagged on the row.
 * - **That these figures may be ahead of the conclusions.** The totals here are computed
 *   from the records as they stand; the Requirements destination shows what was concluded
 *   when it was last run. When those differ, saying so is the whole difference between a
 *   product that is trustworthy and one that is merely confident.
 *
 * No figure on this screen is computed in the browser (CLAUDE.md §8). Every number,
 * including each trip's counted days, is passed through from `GET /timeline`.
 */
export function ResidenceTimeline({ caseId }: { caseId: string }) {
  const timeline = useTimeline(caseId);

  if (timeline.isPending) {
    return (
      <p role="status" style={{ color: "var(--cw-text-muted)" }}>
        Loading your timeline…
      </p>
    );
  }

  if (timeline.isError) {
    return (
      <div role="alert" style={cardStyle}>
        <p style={errorTextStyle}>We couldn’t load your timeline.</p>
        <button type="button" onClick={() => void timeline.refetch()} style={buttonStyle}>
          Try again
        </button>
      </div>
    );
  }

  if (timeline.data === null) {
    return (
      <div style={cardStyle}>
        <p>
          Your timeline is measured against your proposed application date, and you haven’t
          chosen one yet.
        </p>
        <p style={{ marginTop: "var(--cw-space-3)" }}>
          <a href={`/cases/${caseId}/data`} style={{ color: "var(--cw-accent)" }}>
            Choose an application date
          </a>{" "}
          to see your qualifying period and how your trips count against it.
        </p>
      </div>
    );
  }

  return <TimelineTable timeline={timeline.data} caseId={caseId} />;
}

function days(count: number): string {
  return count === 1 ? "1 day" : `${count} days`;
}

/**
 * Held back because a document disputes its dates, rather than because it was never
 * confirmed. Both fail the trust gate; only one is fixed by confirming.
 *
 * Read from `date_confidence` rather than from a dedicated flag: the server sets it to
 * CONFLICTING on exactly the trips it excluded, so the two cannot drift apart.
 */
function isDisputed(trip: TimelineTrip): boolean {
  return trip.date_confidence === "CONFLICTING";
}

/** Why a trip's contribution differs from its length, or null when it does not. */
function countingNote(trip: TimelineTrip): string | null {
  if (trip.is_outside_window) {
    return "Falls entirely outside your qualifying period, so none of it counts. Kept for your records.";
  }
  if (trip.counted_days !== trip.absent_days) {
    const outside = trip.absent_days - trip.counted_days;
    // Agreement matters here: the boundary case is almost always one day, and "1 day fall
    // outside" is the sentence a reader stops on when they are already unsure whether to
    // trust the arithmetic.
    return (
      `${days(outside)} of this trip ${outside === 1 ? "falls" : "fall"} outside your ` +
      `qualifying period, so ${days(trip.counted_days)} ${trip.counted_days === 1 ? "counts" : "count"}.`
    );
  }
  return null;
}

/**
 * Why trips are missing from the confirmed totals, named by reason rather than by count.
 *
 * This said "N trips are not confirmed" until a trip could also be held back by a document
 * disputing its dates. A disputed trip *is* confirmed, so the old sentence told a user who
 * had just confirmed a date that they had not — and the remedy it implies cannot resolve a
 * conflict.
 */
function heldBackClause(totals: Timeline["totals"]): string {
  const conflicted = totals.conflicted_trip_count;
  const unconfirmed = totals.held_back_trip_count - conflicted;
  const trips = (n: number) => (n === 1 ? "1 trip" : `${n} trips`);
  const are = (n: number) => (n === 1 ? "is" : "are");

  if (conflicted > 0 && unconfirmed > 0) {
    return (
      `${trips(unconfirmed)} ${are(unconfirmed)} not confirmed and ` +
      `${trips(conflicted)} ${are(conflicted)} disputed by a document, so they are left out ` +
      "of those totals"
    );
  }
  if (conflicted > 0) {
    return (
      `${trips(conflicted)} ${are(conflicted)} disputed by a document and ` +
      `${conflicted === 1 ? "is" : "are"} left out of those totals`
    );
  }
  return `${trips(unconfirmed)} ${are(unconfirmed)} not confirmed and ${
    unconfirmed === 1 ? "is" : "are"
  } left out of those totals`;
}

function TimelineTable({ timeline, caseId }: { timeline: Timeline; caseId: string }) {
  const { totals } = timeline;

  return (
    <>
      <section aria-labelledby="timeline-window-heading" style={cardStyle}>
        <h3 id="timeline-window-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
          The period being measured
        </h3>
        {/*
          A definition list rather than rows interleaved into the table. These are derived
          boundaries, not travel records, and putting them in the same table would make a
          linear reader parse two kinds of thing under one set of column headers.
        */}
        <dl className="cw-timeline__boundaries">
          <div>
            <dt>Five-year qualifying period</dt>
            <dd>
              {formatDate(timeline.qualifying_period_start)} to{" "}
              {formatDate(timeline.qualifying_period_end)}
            </dd>
          </div>
          <div>
            <dt>First day tested</dt>
            <dd>
              {formatDate(timeline.presence_anchor)}
              <span className="cw-timeline__note">
                {/* Three states, not two. "You were in the UK" is a claim about where the
                    user was, and a record held back from the confirmed totals — unconfirmed,
                    or disputed by a document — is not grounds for making it. The middle case
                    says what is known and what is not, matching the presence rule's own
                    INCOMPLETE rather than picking one of its other two answers. */}
                {timeline.presence_anchor_is_absent
                  ? " — you were outside the UK on this day."
                  : timeline.presence_anchor_is_absent_including_all_records
                    ? " — a trip that is left out of your confirmed totals covers this day, so whether you were in the UK is unsettled."
                    : " — you were in the UK on this day."}
              </span>
            </dd>
          </div>
          <div>
            <dt>Final twelve months</dt>
            <dd>
              {formatDate(timeline.final_year_start)} to {formatDate(timeline.final_year_end)}
            </dd>
          </div>
          <div>
            <dt>Proposed application date</dt>
            <dd>
              {formatDate(timeline.application_date)}
              <span className="cw-timeline__note">
                {" — "}
                <a href={`/cases/${caseId}/data`}>preview a different date</a>
              </span>
            </dd>
          </div>
        </dl>

        <p className="cw-timeline__totals">
          <strong>{days(totals.qualifying_period_days)}</strong> outside the UK across the
          qualifying period, and <strong>{days(totals.final_year_days)}</strong> in the final
          twelve months, from {totals.trip_count} recorded{" "}
          {totals.trip_count === 1 ? "trip" : "trips"}.
          {totals.held_back_trip_count > 0 && (
            <>
              {" "}
              {heldBackClause(totals)}; counting them would give{" "}
              {days(totals.qualifying_period_days_including_all_records)} and{" "}
              {days(totals.final_year_days_including_all_records)}.
            </>
          )}
        </p>

        {timeline.assessment_is_stale && (
          <p className="cw-timeline__behind" role="status">
            These figures are current. Your residence conclusions were reached before your
            latest change — recheck them on Requirements.
          </p>
        )}
      </section>

      <section aria-labelledby="timeline-trips-heading" style={cardStyle}>
        <h3 id="timeline-trips-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
          Every trip, in order
        </h3>

        {/* The shape, above the table it describes. Never instead of it, and never behind
            a toggle: a control that can hide the accessible version is a control that
            eventually does. */}
        {timeline.trips.length > 0 && <TimelineBand timeline={timeline} />}

        {timeline.trips.length === 0 ? (
          <p style={{ marginTop: "var(--cw-space-3)", color: "var(--cw-text-muted)" }}>
            You haven’t recorded any trips. With none recorded, your absence totals are
            zero — add them on the Case data page so they can be counted.
          </p>
        ) : (
          <div className="cw-trips-wrap">
            {/*
              Explicit roles on every element. Below 34rem the stylesheet switches these to
              `display: block` so the columns can stack, and that strips the implicit table
              semantics — the roles are what keep a row a row at 200% zoom.
            */}
            <table className="cw-timeline-table" role="table">
              {/* The window is stated in full above; repeating it here was the third
                  time on one screen. The caption's job is ordering and what the days are
                  measured against, which "counted" carries. */}
              <caption>Your trips, earliest first</caption>
              {/*
                Three columns, not five. Departure and return are one fact — when the trip
                was — and a separate "Record" column held the word "Confirmed" twelve times
                over, which is twelve repetitions of the unremarkable and one of the thing
                that matters. Flagging only the exception is the convention the travel
                table already set.
              */}
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">
                    Destination
                  </th>
                  <th role="columnheader" scope="col">
                    Trip dates
                  </th>
                  <th role="columnheader" scope="col">
                    Days counted
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {timeline.trips.map((trip) => (
                  <TripRow
                    key={trip.travel_record_id}
                    trip={trip}
                    assessmentIsStale={timeline.assessment_is_stale}
                  />
                ))}
              </tbody>
              <tfoot role="rowgroup">
                <tr role="row">
                  <th role="rowheader" scope="row" colSpan={2}>
                    Total counted inside the qualifying period
                  </th>
                  <td role="cell" className="cw-timeline-table__days">
                    <span className="cw-figure">{days(totals.qualifying_period_days)}</span>
                    {/* The visible cell is a figure; the sentence behind it is what a
                        screen reader needs, since "439 days" alone says nothing about
                        which days or measured how. */}
                    <span className="cw-visually-hidden">
                      , the union of your counted trips’ days inside{" "}
                      {formatDate(timeline.qualifying_period_start)} to{" "}
                      {formatDate(timeline.qualifying_period_end)}. Overlapping days are
                      counted once.
                      {totals.held_back_trip_count > 0 &&
                        ` ${heldBackClause(totals)}.`}
                    </span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function TripRow({
  trip,
  assessmentIsStale,
}: {
  trip: TimelineTrip;
  assessmentIsStale: boolean;
}) {
  const note = countingNote(trip);
  return (
    <tr role="row" className={trip.is_outside_window ? "cw-timeline-table__row--outside" : ""}>
      <td role="cell" className="cw-timeline-table__destination">
        {trip.destination_label}
        {trip.covers_presence_anchor && (
          <span className="cw-timeline-table__anchor">Covers the first day tested</span>
        )}
        {/* Only the exception is flagged. Confirmed-and-exact is the ordinary state and
            labelling every row with it buries the one row that is not.

            Two exceptions now, and they must not share a label. "Confirm its dates" is a
            dead end for a disputed trip: the user already confirmed them, and confirming
            again cannot make two sources agree. Sending someone to repeat an action that
            cannot work is worse than saying nothing. */}
        {!trip.is_trusted && (
          <span className="cw-timeline-table__flag">
            {isDisputed(trip) ? (
              <>
                <StatusBadge
                  colorVar="--cw-status-inconsistent"
                  surfaceVar="--cw-status-inconsistent-surface"
                  glyph="!"
                  label="Dates disputed"
                />
                <span className="cw-timeline-table__note">
                  A document you attached gives different dates, so this trip is left out of
                  your confirmed totals.{" "}
                  {/* The conflict on this row is derived live; the Issues queue is derived
                      from the last assessment. Between confirming the document's value and
                      rechecking, the flag is here and the queue item is not — so sending
                      the user to Issues would send them somewhere the problem does not yet
                      appear, and a queue that looks empty reads as a problem that went
                      away. */}
                  {assessmentIsStale
                    ? "Recheck your requirements and it will appear in Issues."
                    : "You can resolve it from Issues."}
                </span>
              </>
            ) : (
              <>
                <StatusBadge
                  colorVar="--cw-status-not-assessed"
                  surfaceVar="--cw-status-not-assessed-surface"
                  glyph="?"
                  label="Not confirmed"
                />
                <span className="cw-timeline-table__note">
                  Left out of your confirmed totals until you confirm its dates.
                </span>
              </>
            )}
          </span>
        )}
        {trip.overlaps_with.length > 0 && (
          <span className="cw-timeline-table__note">
            Shares days with another trip. The overlap is counted once, but one of the two
            records is likely wrong.
          </span>
        )}
      </td>
      <td role="cell" className="cw-timeline-table__dates">
        {formatDate(trip.departure_date)}
        {" to "}
        {formatDate(trip.return_date)}
      </td>
      <td role="cell" className="cw-timeline-table__days">
        <span className="cw-figure">{days(trip.counted_days)}</span>
        {/* Departure and return days are UK days and never count, which is the single
            most common reason a user's own arithmetic disagrees with ours. Said once per
            row, to the reader who cannot see the column heading alongside the figure. */}
        <span className="cw-visually-hidden">
          counted inside your qualifying period, out of {days(trip.absent_days)} away. The
          days you left and returned are UK days and never count.
        </span>
        {note && <span className="cw-timeline-table__note">{note}</span>}
      </td>
    </tr>
  );
}
