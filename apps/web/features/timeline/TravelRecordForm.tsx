"use client";

import type { components } from "@cw/api-client";
import { useEffect, useRef, useState } from "react";

import { Combobox } from "./Combobox";
import { COUNTRY_NAMES } from "./countries";
import { yearsFromTodayISO } from "./dates";
import { formatDate } from "@/features/requirements/dates";
import { Field, buttonStyle, errorTextStyle, inputStyle, secondaryButtonStyle, selectStyle } from "@/components/ui";

type DateConfidence = components["schemas"]["DateConfidence"];
type ReviewState = components["schemas"]["TravelReviewState"];

// Typo-guard bounds for the native date inputs, not business rules.
//
// The floor is six years back. The application date cannot be in the past, so the
// qualifying period never starts more than five years before today, and a trip ending
// before that can affect nothing. The sixth year is for a trip that leaves before the
// period and comes back inside it, which counts in part and has to be enterable. It was
// twenty years, which only made a mistyped year easier to keep.
//
// An existing trip older than the floor lowers it for its own edit form (`floorFor`), or
// the browser would refuse to save that trip at all, even to change its reason.
const MIN_DATE = yearsFromTodayISO(-6);
const MAX_DATE = yearsFromTodayISO(10);

function floorFor(initial: TravelFormValues): string {
  return [MIN_DATE, initial.departure_date, initial.return_date]
    .filter((d) => d !== "")
    .sort()[0]!;
}

/** Whether a date input's value is a whole, plausible date rather than one mid-typing. */
function isPlausible(value: string, floor: string): boolean {
  return value !== "" && value >= floor && value <= MAX_DATE;
}

export interface TravelFormValues {
  destination_label: string;
  departure_date: string;
  return_date: string;
  date_confidence: DateConfidence;
  review_state: ReviewState;
  notes: string;
  reason: string;
}

export const EMPTY_TRAVEL_FORM: TravelFormValues = {
  destination_label: "",
  departure_date: "",
  return_date: "",
  date_confidence: "EXACT",
  review_state: "CONFIRMED",
  notes: "",
  reason: "",
};

/**
 * One question for two fields.
 *
 * `date_confidence` and `review_state` are independent in the model (§11.4, §11.5) and stay
 * so: the system sets states of its own (DRAFT, and CONFLICTING when a document disputes a
 * trip), the CSV import has a column for each, and the travel list marks them differently.
 * But to someone typing in a trip they were two dropdowns doing one job, since either one
 * off its default holds the trip back from the confirmed totals (RULES_SPEC §6.1). The
 * combinations a person can actually mean are three, so the form asks one question with
 * three answers and writes both fields.
 */
const CERTAINTY_OPTIONS: { key: string; label: string; confidence: DateConfidence; review: ReviewState }[] = [
  { key: "EXACT:CONFIRMED", label: "I have the exact dates", confidence: "EXACT", review: "CONFIRMED" },
  {
    key: "ESTIMATED:CONFIRMED",
    label: "The dates are approximate",
    confidence: "ESTIMATED",
    review: "CONFIRMED",
  },
  {
    key: "UNKNOWN:UNCERTAIN",
    label: "I'm not sure about this trip",
    confidence: "UNKNOWN",
    review: "UNCERTAIN",
  },
];

const CONFIDENCE_WORDS: Record<string, string> = {
  EXACT: "exact dates",
  ESTIMATED: "approximate dates",
  UNKNOWN: "dates not known",
  CONFLICTING: "dates in conflict",
};
const REVIEW_WORDS: Record<string, string> = {
  CONFIRMED: "confirmed",
  UNCERTAIN: "trip unsure",
  DRAFT: "not yet confirmed",
};

/** The trip form lives in a dialog, so its fields fill it: one clean edge for labels,
 *  hints, inputs and buttons. The 24rem field width is for full pages, where a date
 *  stretched across the column would look empty. */
const FULL: React.CSSProperties = { width: "100%", maxWidth: "none" };

const certaintyKey = (confidence: string, review: string) => `${confidence}:${review}`;

/**
 * A combination the three answers do not cover, kept as an answer of its own.
 *
 * A trip imported from a CSV can hold, say, exact dates and UNCERTAIN. Mapping it to the
 * nearest answer would change a version field the user never touched, so saving only a
 * reason would append a version and stale the assessment (ADR-0035). So the stored
 * combination is offered as it is, and kept unless the user picks another answer.
 */
function recordedOption(initial: TravelFormValues) {
  const key = certaintyKey(initial.date_confidence, initial.review_state);
  if (CERTAINTY_OPTIONS.some((o) => o.key === key)) return null;
  const words = `${CONFIDENCE_WORDS[initial.date_confidence] ?? initial.date_confidence}, ${
    REVIEW_WORDS[initial.review_state] ?? initial.review_state
  }`;
  return {
    key,
    label: `As recorded: ${words}`,
    confidence: initial.date_confidence,
    review: initial.review_state,
  };
}

/**
 * Controlled add/edit form for one travel record. Owns its field values and the one
 * client-side check that gives immediate feedback (departure not after return); the
 * server remains authoritative. On a client-valid submit it hands the values up; the
 * parent performs the write and passes back any server error to show.
 */
export function TravelRecordForm({
  idPrefix,
  initial = EMPTY_TRAVEL_FORM,
  submitLabel,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  period,
}: {
  idPrefix: string;
  /** The qualifying period, from the server, to say where trips count. Absent without an
   *  application date. */
  period?: { start: string; end: string } | undefined;
  initial?: TravelFormValues;
  submitLabel: string;
  submitting: boolean;
  serverError?: string | undefined;
  onSubmit: (values: TravelFormValues) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<TravelFormValues>(initial);
  const [orderError, setOrderError] = useState(false);
  // Whether the return date is the user's own choice. Until it is, it follows the
  // departure date. An edit opens with one already chosen.
  const [returnChosen, setReturnChosen] = useState(initial.return_date !== "");
  const [notesOpen, setNotesOpen] = useState(initial.notes !== "");
  // Set by "Add a note" only, so an edit that opens with a note does not steal focus.
  const focusNotes = useRef(false);
  useEffect(() => {
    if (!notesOpen || !focusNotes.current) return;
    focusNotes.current = false;
    document.getElementById(`${idPrefix}-notes`)?.focus();
  }, [notesOpen, idPrefix]);
  const floor = floorFor(initial);
  const recorded = recordedOption(initial);
  const certaintyOptions = recorded ? [...CERTAINTY_OPTIONS, recorded] : CERTAINTY_OPTIONS;

  function set<K extends keyof TravelFormValues>(key: K, v: TravelFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: v }));
    setOrderError(false);
  }

  /**
   * Setting the departure date seeds an empty return date with the same day.
   *
   * **Why this is not the anchoring the product spends so much effort preventing.** Blind
   * entry exists because a *machine's* reading, shown beside an empty box, is a value a
   * person will type out instead of reading the page. The risk is deferring to the
   * machine. Here the only value on offer is one the user typed thirty seconds earlier, in
   * a field about their own history, with no document and no proposal in sight.
   *
   * **Why seeding the value rather than setting `min`.** The reported problem was that the
   * return picker opens on *today*, five years of clicking from a trip in 2021. A `min`
   * does not move it — an empty date input opens at today whenever today is in range — and
   * it actively breaks the error path, because a value below `min` is `rangeUnderflow` and
   * the browser then refuses the submit itself, replacing this app's bound message with a
   * native bubble. A picker opens at its *value*, so seeding is both the thing that works
   * and the thing that changes nothing about validation.
   *
   * **What it costs, stated rather than buried.** `required` no longer catches a forgotten
   * return date — an omission becomes a one-day trip instead of a refusal. Accepted
   * because such a trip is legible in the table immediately afterwards ("12 Dec 2021 to
   * 12 Dec 2021"), and a wrong value the user can see beats a right value they never
   * reached.
   */
  function setDeparture(value: string) {
    setValues((prev) => ({
      ...prev,
      departure_date: value,
      // **Follows until chosen, and only a whole date.** Typing "10 12 2021" into a native
      // date input passes through year 0002 after the first digit of the year: a valid
      // date, so it fired a change. The first version copied the departure only into an
      // *empty* return date, so the return date kept 10 December 0002 while the departure
      // went on to 2021. Found by typing into the form in Chrome; the test set the value
      // in one step and never saw the in-between state.
      return_date: returnChosen ? prev.return_date : isPlausible(value, floor) ? value : "",
    }));
    setOrderError(false);
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (values.departure_date && values.return_date && values.departure_date > values.return_date) {
      setOrderError(true);
      document.getElementById(`${idPrefix}-return`)?.focus();
      return;
    }
    onSubmit(values);
  }

  const id = (name: string) => `${idPrefix}-${name}`;

  return (
    // `minmax(0, 1fr)`: a bare grid column sizes to its widest child's min-content, and the
    // certainty select's longest option made every field 14px wider than a 320px dialog.
    <form
      onSubmit={handleSubmit}
      style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "var(--cw-space-4)" }}
    >
      {/* No hint: the suggestions appearing as you type say what the old one did. */}
      <Field id={id("destination")} label="Destination" fullWidth>
        <Combobox
          id={id("destination")}
          value={values.destination_label}
          options={COUNTRY_NAMES}
          onChange={(v) => set("destination_label", v)}
          required
          maxLength={120}
          fullWidth
        />
      </Field>

      {/* The two dates side by side, under the one hint that is about both. It sat under
          Departure alone, and a hint per date was a second copy of the same sentence. The
          group is named for assistive technology, and the hint is also bound to Departure
          directly, since not every screen reader reads a group's description. */}
      <fieldset className="cw-trip-dates">
        <legend className="cw-visually-hidden">Trip dates</legend>
        {period ? (
          <p id={id("period")} className="cw-trip-dates__hint">
            Trips between {formatDate(period.start)} and {formatDate(period.end)} count
            towards your application.
          </p>
        ) : null}
        <div className="cw-trip-dates__pair">
          <Field id={id("departure")} label="Departure date" fullWidth>
            <input
              id={id("departure")}
              type="date"
              value={values.departure_date}
              required
              min={floor}
              max={MAX_DATE}
              className="cw-date-input"
              onChange={(e) => setDeparture(e.target.value)}
              aria-describedby={period ? id("period") : undefined}
              style={{ ...inputStyle, ...FULL }}
            />
          </Field>

          <Field
        fullWidth
            id={id("return")}
            label="Return date"
            error={orderError ? "Return date can’t be before the departure date." : undefined}
            errorIsLive={false} // focus moves here on error, which announces the bound message
          >
            <input
              id={id("return")}
              type="date"
              value={values.return_date}
              required
              // **Deliberately not `min={values.departure_date}`**, which is the obvious thing
              // and is wrong here. A `min` the value falls below makes the field
              // `rangeUnderflow`, so the browser blocks submission itself, and our bound,
              // focus-managed "Return date can’t be before the departure date." never renders.
              // The ordering check belongs in `handleSubmit`, where it can produce a message
              // this app controls, and on the server after that.
              min={floor}
              max={MAX_DATE}
              className="cw-date-input"
              onChange={(e) => {
                setReturnChosen(true);
                set("return_date", e.target.value);
              }}
              style={{ ...inputStyle, ...FULL }}
            />
          </Field>
        </div>
      </fieldset>

      <Field
        fullWidth
        id={id("certainty")}
        label="How sure are you about this trip?"
        hint="Only exact dates you're sure of count towards your totals."
      >
        <select
          id={id("certainty")}
          value={certaintyKey(values.date_confidence, values.review_state)}
          onChange={(e) => {
            const chosen = certaintyOptions.find((o) => o.key === e.target.value);
            if (!chosen) return;
            setValues((prev) => ({
              ...prev,
              date_confidence: chosen.confidence,
              review_state: chosen.review,
            }));
          }}
          style={{ ...selectStyle, ...FULL }}
        >
          {certaintyOptions.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      {/* Above Notes, because it is the one that leaves the workspace: it is the "Reason
          for trip" column of the travel list handed over with an application. Changing it
          alone changes no conclusion and makes nothing out of date (ADR-0035). */}
      <Field
        fullWidth
        id={id("reason")}
        label="Reason for trip"
        // Expected, not enforced (ADR-0035). The application form asks for a reason for
        // every trip, so the label no longer says optional. Saving without one stays
        // allowed: a trip left out for want of a reason under-counts absences, where a
        // missing reason only matters when the list is handed over, and it says so there.
        hint="The application form asks for one, for example Holiday or Visiting family."
      >
        <input
          id={id("reason")}
          value={values.reason}
          maxLength={200}
          onChange={(e) => set("reason", e.target.value)}
          style={{ ...inputStyle, ...FULL }}
        />
      </Field>

      {/* Behind a disclosure: the least used field, and optional, so it no longer takes a
          row from every trip. Open from the start on a trip that already has a note, so an
          edit never hides what is there. */}
      {notesOpen ? (
        <Field id={id("notes")} label="Notes" fullWidth hint="Optional. Kept in the workspace, not on your travel list.">
          <input
            id={id("notes")}
            value={values.notes}
            onChange={(e) => set("notes", e.target.value)}
            style={{ ...inputStyle, ...FULL }}
          />
        </Field>
      ) : (
        <p style={{ margin: 0 }}>
          <button
            type="button"
            className="cw-trip-form__disclosure"
            aria-expanded={false}
            onClick={() => {
              // Focus follows in the effect above, once the field has mounted. A frame
              // callback raced the dialog's own focus handling in Chrome and lost, leaving
              // focus nowhere; jsdom passed either way.
              focusNotes.current = true;
              setNotesOpen(true);
            }}
          >
            Add a note
          </button>
        </p>
      )}

      <div style={{ display: "flex", gap: "var(--cw-space-3)", alignItems: "center", flexWrap: "wrap" }}>
        <button type="submit" disabled={submitting} style={buttonStyle}>
          {submitting ? "Saving…" : submitLabel}
        </button>
        <button type="button" onClick={onCancel} style={secondaryButtonStyle}>
          Cancel
        </button>
        {serverError && (
          <span role="alert" style={errorTextStyle}>
            {serverError}
          </span>
        )}
      </div>
    </form>
  );
}
