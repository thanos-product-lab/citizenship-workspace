"use client";

import type { components } from "@cw/api-client";
import { useState } from "react";

import { Field, buttonStyle, errorTextStyle, inputStyle, secondaryButtonStyle } from "./ui";

type DateConfidence = components["schemas"]["DateConfidence"];
type ReviewState = components["schemas"]["TravelReviewState"];

export interface TravelFormValues {
  destination_label: string;
  destination_country_code: string;
  departure_date: string;
  return_date: string;
  date_confidence: DateConfidence;
  review_state: ReviewState;
  notes: string;
}

export const EMPTY_TRAVEL_FORM: TravelFormValues = {
  destination_label: "",
  destination_country_code: "",
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
      <Field id={id("destination")} label="Destination">
        <input
          id={id("destination")}
          value={values.destination_label}
          required
          maxLength={120}
          onChange={(e) => set("destination_label", e.target.value)}
          style={inputStyle}
        />
      </Field>

      <Field id={id("country")} label="Country code" hint="Optional, two letters (e.g. ES).">
        <input
          id={id("country")}
          value={values.destination_country_code}
          maxLength={2}
          onChange={(e) => set("destination_country_code", e.target.value)}
          style={{ ...inputStyle, maxWidth: "8rem" }}
        />
      </Field>

      <Field id={id("departure")} label="Departure date">
        <input
          id={id("departure")}
          type="date"
          value={values.departure_date}
          required
          onChange={(e) => set("departure_date", e.target.value)}
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
