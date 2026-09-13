"use client";

import type { components } from "@cw/api-client";
import { useState } from "react";

import { Combobox } from "./Combobox";
import { COUNTRY_NAMES } from "./countries";
import { yearsFromTodayISO } from "./dates";
import { Field, buttonStyle, errorTextStyle, inputStyle, secondaryButtonStyle } from "@/components/ui";

type DateConfidence = components["schemas"]["DateConfidence"];
type ReviewState = components["schemas"]["TravelReviewState"];

// Typo-guard bounds for the native date inputs: generous enough never to reject a real
// past trip or a forward-planned one, tight enough to keep a mistyped year out.
const MIN_DATE = yearsFromTodayISO(-20);
const MAX_DATE = yearsFromTodayISO(10);

export interface TravelFormValues {
  destination_label: string;
  departure_date: string;
  return_date: string;
  date_confidence: DateConfidence;
  review_state: ReviewState;
  notes: string;
}

export const EMPTY_TRAVEL_FORM: TravelFormValues = {
  destination_label: "",
  departure_date: "",
  return_date: "",
  date_confidence: "EXACT",
  review_state: "CONFIRMED",
  notes: "",
};

// CONFLICTING/DRAFT are system states (they arise from evidence review, not manual
// entry), so they are not offered here — a user marks a trip Exact/Estimated/Unknown
// and Confirmed/Uncertain, the two independent trust dimensions (§11.4–11.5).
const CONFIDENCE_OPTIONS: { value: DateConfidence; label: string }[] = [
  { value: "EXACT", label: "Exact dates" },
  { value: "ESTIMATED", label: "Estimated" },
  { value: "UNKNOWN", label: "Not sure" },
];

const REVIEW_OPTIONS: { value: ReviewState; label: string }[] = [
  { value: "CONFIRMED", label: "Confirmed" },
  { value: "UNCERTAIN", label: "Uncertain" },
];

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
}: {
  idPrefix: string;
  initial?: TravelFormValues;
  submitLabel: string;
  submitting: boolean;
  serverError?: string | undefined;
  onSubmit: (values: TravelFormValues) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<TravelFormValues>(initial);
  const [orderError, setOrderError] = useState(false);

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
      return_date: prev.return_date === "" ? value : prev.return_date,
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
    <form onSubmit={handleSubmit} style={{ display: "grid", gap: "var(--cw-space-4)" }}>
      <Field id={id("destination")} label="Destination" hint="Start typing a country, or enter your own.">
        <Combobox
          id={id("destination")}
          value={values.destination_label}
          options={COUNTRY_NAMES}
          onChange={(v) => set("destination_label", v)}
          required
          maxLength={120}
        />
      </Field>

      <Field id={id("departure")} label="Departure date">
        <input
          id={id("departure")}
          type="date"
          value={values.departure_date}
          required
          min={MIN_DATE}
          max={MAX_DATE}
          className="cw-date-input"
          onChange={(e) => setDeparture(e.target.value)}
          style={inputStyle}
        />
      </Field>

      <Field
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
          // `rangeUnderflow`, so the browser blocks submission itself — our bound,
          // focus-managed "Return date can’t be before the departure date." never renders
          // and the user gets an unstyled native bubble instead. The existing test caught
          // it immediately. The ordering check belongs in `handleSubmit`, where it can
          // produce a message this app controls, and on the server after that.
          min={MIN_DATE}
          max={MAX_DATE}
          className="cw-date-input"
          onChange={(e) => set("return_date", e.target.value)}
          style={inputStyle}
        />
      </Field>

      <Field id={id("confidence")} label="Date certainty">
        <select
          id={id("confidence")}
          value={values.date_confidence}
          onChange={(e) => set("date_confidence", e.target.value as DateConfidence)}
          style={inputStyle}
        >
          {CONFIDENCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      <Field id={id("review")} label="Status" hint="Uncertain trips are kept separate from confirmed ones.">
        <select
          id={id("review")}
          value={values.review_state}
          onChange={(e) => set("review_state", e.target.value as ReviewState)}
          style={inputStyle}
        >
          {REVIEW_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </Field>

      <Field id={id("notes")} label="Notes" hint="Optional.">
        <input
          id={id("notes")}
          value={values.notes}
          onChange={(e) => set("notes", e.target.value)}
          style={inputStyle}
        />
      </Field>

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
