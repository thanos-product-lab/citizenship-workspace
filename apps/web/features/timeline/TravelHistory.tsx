"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched } from "@/lib/queries";

import { ConfirmDialog } from "./ConfirmDialog";
import { countryCodeFor } from "./countries";
import { CsvImport } from "./CsvImport";
import { Dialog } from "./Dialog";
import { TravelRecordForm } from "./TravelRecordForm";
import type { TravelFormValues } from "./TravelRecordForm";
import {
  StatusBadge,
  buttonStyle,
  cardStyle,
  dateCellStyle,
  errorTextStyle,
  firstColStyle,
  secondaryButtonStyle,
  tdStyle,
  thStyle,
} from "./ui";

type Travel = components["schemas"]["TravelRecordResponse"];
type LoadState = "loading" | "error" | "ready";
type Mode = { kind: "none" } | { kind: "add" } | { kind: "edit"; id: string };

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Format an ISO YYYY-MM-DD without constructing a Date (avoids any timezone shift). */
function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  const month = MONTHS[Number(m) - 1] ?? m;
  return `${Number(d)} ${month} ${y}`;
}

interface Trust {
  confirmed: boolean;
  label: string;
  detail: string;
  colorVar: string;
  surfaceVar: string;
  glyph: string;
}

// A record is trusted only when confirmed AND its dates are exact (the M3B gate); any
// other combination is surfaced as "Uncertain" so unconfirmed records stay visibly
// distinct (§8.4). Status is carried by badge text + glyph, never colour alone.
// Uncertain is deliberately neutral, not amber: amber ("near threshold") is a rules
// concept, and an unconfirmed input is not a rules state — borrowing that hue would
// imply a meaning M3A does not compute.
function trust(r: Travel): Trust {
  const confirmed = r.review_state === "CONFIRMED" && r.date_confidence === "EXACT";
  const detail =
    r.review_state !== "CONFIRMED"
      ? "Marked uncertain"
      : r.date_confidence === "ESTIMATED"
        ? "Estimated dates"
        : r.date_confidence === "CONFLICTING"
          ? "Conflicting dates"
          : r.date_confidence === "UNKNOWN"
            ? "Dates not known"
            : "";
  return confirmed
    ? {
        confirmed,
        label: "Confirmed",
        detail,
        colorVar: "--cw-status-supported",
        surfaceVar: "--cw-status-supported-surface",
        glyph: "✓",
      }
    : {
        confirmed,
        label: "Uncertain",
        detail,
        colorVar: "--cw-status-not-assessed",
        surfaceVar: "--cw-status-not-assessed-surface",
        glyph: "○",
      };
}

function toBody(values: TravelFormValues) {
  return {
    destination_label: values.destination_label,
    // The code is derived from the label, never asked for: a country name maps to its
    // ISO code, anything else has none. No rule depends on it (RULES_SPEC §11).
    destination_country_code: countryCodeFor(values.destination_label),
    departure_date: values.departure_date,
    return_date: values.return_date,
    date_confidence: values.date_confidence,
    review_state: values.review_state,
    notes: values.notes || null,
  };
}

function toForm(r: Travel): TravelFormValues {
  return {
    destination_label: r.destination_label,
    departure_date: r.departure_date,
    return_date: r.return_date,
    date_confidence: r.date_confidence as TravelFormValues["date_confidence"],
    review_state: r.review_state as TravelFormValues["review_state"],
    notes: r.notes ?? "",
  };
}

/**
 * The travel-history surface: an accessible chronological table of trips with
 * confirmed and uncertain records visibly distinct, plus manual add/edit/remove and
 * CSV import. All totals and calculations are deliberately absent — this is the input
 * layer; the assessment view arrives in a later milestone.
 */
export function TravelHistory({
  caseId,
}: {
  caseId: string;
}) {
  const api = useApiClient();
  const client = useQueryClient();
  const [records, setRecords] = useState<Travel[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [mode, setMode] = useState<Mode>({ kind: "none" });
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | undefined>();
  const [removeId, setRemoveId] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [notice, setNotice] = useState("");
  const headingRef = useRef<HTMLHeadingElement>(null);

  const load = useCallback(
    (opts?: { notice?: string }) => {
      let active = true;
      void api
        .GET("/api/v1/cases/{case_id}/travel-records", { params: { path: { case_id: caseId } } })
        .then(({ data, error }) => {
          if (!active) return;
          if (error || !data) {
            setState("error");
            return;
          }
          setRecords(data);
          setState("ready");
          if (opts?.notice) {
            setNotice(opts.notice);
            headingRef.current?.focus();
          }
        });
      return () => {
        active = false;
      };
    },
    [api, caseId],
  );

  useEffect(() => load(), [load]);

  function closeForm() {
    setMode({ kind: "none" });
    setFormError(undefined);
    setFormBusy(false);
  }

  // Cancelling the form dialog returns focus to whichever control opened it — the row's
  // Edit button, or the "Add a trip" button — rather than dropping it to <body>. Capture
  // the trigger id before closing (which clears `mode`), then focus after the close commits.
  function cancelForm() {
    const returnId = mode.kind === "edit" ? `edit-${mode.id}` : "add-trip";
    flushSync(closeForm);
    document.getElementById(returnId)?.focus();
  }

  // Cancelling the remove dialog returns focus to the row's Remove button (the dialog
  // owns focus while open; only the parent knows the trigger). flushSync closes it before
  // we focus, so the trigger is back in the DOM and reachable.
  function cancelRemove(id: string) {
    flushSync(() => setRemoveId(null));
    document.getElementById(`remove-${id}`)?.focus();
  }

  // On a successful add/edit/remove the dialog unmounts. Close it and move focus to the
  // heading *synchronously* (flushSync) so focus never lands on <body> during the async
  // reload — the reload then announces the notice via the polite region. Mirrors the
  // cancel paths' discipline.
  function closeToHeading(close: () => void) {
    flushSync(close);
    headingRef.current?.focus();
  }

  async function submitAdd(values: TravelFormValues) {
    setFormBusy(true);
    setFormError(undefined);
    const { data, response } = await api.POST("/api/v1/cases/{case_id}/travel-records", {
      params: { path: { case_id: caseId } },
      body: toBody(values),
    });
    setFormBusy(false);
    if (data) {
      closeToHeading(closeForm);
      load({ notice: "Trip added." });
      void assessmentTouched(client, caseId);
      return;
    }
    setFormError(response?.status === 422 ? "Please check the dates and try again." : "Something went wrong.");
  }

  async function submitEdit(id: string, values: TravelFormValues) {
    const record = records.find((r) => r.id === id);
    if (!record) return;
    setFormBusy(true);
    setFormError(undefined);
    const { data, response } = await api.PATCH(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}",
      {
        params: { path: { case_id: caseId, travel_record_id: id } },
        body: { ...toBody(values), expected_revision: record.revision },
      },
    );
    setFormBusy(false);
    if (data) {
      closeToHeading(closeForm);
      load({ notice: "Trip updated." });
      void assessmentTouched(client, caseId);
      return;
    }
    if (response?.status === 409) {
      setFormError("This trip changed elsewhere. Cancel and reload.");
      return;
    }
    setFormError(response?.status === 422 ? "Please check the dates and try again." : "Something went wrong.");
  }

  async function doRemove(record: Travel) {
    setRemoving(true);
    const { data, response } = await api.DELETE(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}",
      {
        params: {
          path: { case_id: caseId, travel_record_id: record.id },
          query: { expected_revision: record.revision },
        },
      },
    );
    closeToHeading(() => {
      setRemoving(false);
      setRemoveId(null);
    });
    if (data) {
      load({ notice: "Trip removed." });
      void assessmentTouched(client, caseId);
      return;
    }
    load({ notice: response?.status === 409 ? "That trip changed elsewhere; reloaded." : "Could not remove the trip." });
  }

  // Sort client-side so the "earliest first" caption is truthful regardless of the
  // endpoint's ordering (the API also sorts, but the caption shouldn't depend on it).
  const sorted = [...records].sort((a, b) => a.departure_date.localeCompare(b.departure_date));
  const removeRecord = removeId ? (records.find((r) => r.id === removeId) ?? null) : null;

  return (
    <section aria-labelledby="travel-heading" style={cardStyle}>
      <h3 ref={headingRef} tabIndex={-1} id="travel-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        Travel history
      </h3>
      <p style={{ marginTop: "var(--cw-space-2)", color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        Every period you spent outside the UK.
      </p>

      {/* Polite region for the result of an add / edit / remove / import. Styled as a
          distinct confirmation (accent, leading check) so it doesn't read as prose;
          the node stays mounted (empty) to keep the live region stable. */}
      <p
        role="status"
        aria-live="polite"
        style={{
          margin: "var(--cw-space-3) 0 0",
          minHeight: "1.25rem",
          color: "var(--cw-accent)",
          fontSize: "var(--cw-text-sm)",
          fontWeight: "var(--cw-weight-medium)",
        }}
      >
        {notice && (
          <>
            <span aria-hidden="true">✓ </span>
            {notice}
          </>
        )}
      </p>

      {state === "loading" && (
        <p role="status" style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-4)" }}>
          Loading trips…
        </p>
      )}

      {state === "error" && (
        <div role="alert" style={{ marginTop: "var(--cw-space-4)" }}>
          <p style={errorTextStyle}>We couldn’t load your travel history.</p>
          <button type="button" onClick={() => load()} style={buttonStyle}>
            Try again
          </button>
        </div>
      )}

      {state === "ready" && (
        <>
          {records.length === 0 ? (
            <p style={{ marginTop: "var(--cw-space-4)" }}>
              No trips recorded yet. Add one below, or import a spreadsheet.
            </p>
          ) : (
            <div style={{ marginTop: "var(--cw-space-4)", overflowX: "auto" }}>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <caption style={{ textAlign: "left", fontSize: "var(--cw-text-xs)", color: "var(--cw-text-subtle)", marginBottom: "var(--cw-space-2)" }}>
                  Your recorded trips, earliest first
                </caption>
                <thead>
                  <tr>
                    <th scope="col" style={firstColStyle(thStyle)}>Destination</th>
                    <th scope="col" style={thStyle}>Dates</th>
                    <th scope="col" style={{ ...thStyle, textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((r) => {
                    const t = trust(r);
                    return (
                      <tr key={r.id}>
                        <td style={firstColStyle({ ...tdStyle, fontWeight: "var(--cw-weight-medium)" })}>
                          {r.destination_label}
                          {/* Confirmed is the quiet default; only uncertain trips are
                              flagged — the exception is what needs the user's attention. */}
                          {!t.confirmed && (
                            <span style={{ display: "block", marginTop: "var(--cw-space-2)", fontWeight: "var(--cw-weight-regular)" }}>
                              <StatusBadge
                                colorVar={t.colorVar}
                                surfaceVar={t.surfaceVar}
                                glyph={t.glyph}
                                label={t.label}
                              />
                              {t.detail && (
                                <span style={{ display: "block", marginTop: "var(--cw-space-1)", fontSize: "var(--cw-text-xs)", color: "var(--cw-text-subtle)" }}>
                                  {t.detail}
                                </span>
                              )}
                            </span>
                          )}
                        </td>
                        <td style={dateCellStyle}>
                          <div>{formatDate(r.departure_date)}</div>
                          <div style={{ color: "var(--cw-text-subtle)" }}>
                            to {formatDate(r.return_date)}
                          </div>
                        </td>
                        <td style={{ ...tdStyle, textAlign: "right", whiteSpace: "nowrap" }}>
                          <span style={{ display: "inline-flex", gap: "var(--cw-space-4)" }}>
                            <button
                              type="button"
                              id={`edit-${r.id}`}
                              onClick={() => {
                                setMode({ kind: "edit", id: r.id });
                                setFormError(undefined);
                              }}
                              className="cw-action"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              id={`remove-${r.id}`}
                              onClick={() => setRemoveId(r.id)}
                              className="cw-action cw-action--muted"
                            >
                              Remove
                            </button>
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {mode.kind === "none" && (
            <button
              type="button"
              id="add-trip"
              onClick={() => {
                setMode({ kind: "add" });
                setFormError(undefined);
              }}
              style={{ ...secondaryButtonStyle, marginTop: "var(--cw-space-4)" }}
            >
              Add a trip
            </button>
          )}

          <CsvImport
            caseId={caseId}
            onImported={(n) => load({ notice: `Imported ${n} ${n === 1 ? "trip" : "trips"}.` })}
          />
        </>
      )}

      <Dialog
        open={mode.kind !== "none"}
        labelledBy="trip-dialog-title"
        onDismiss={cancelForm}
        maxWidth="32rem"
      >
        <h2 id="trip-dialog-title" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
          {mode.kind === "edit" ? "Edit trip" : "Add a trip"}
        </h2>
        <div style={{ marginTop: "var(--cw-space-5)" }}>
          {mode.kind === "edit" ? (
            <TravelRecordForm
              idPrefix="edit"
              initial={toForm(records.find((r) => r.id === mode.id) ?? records[0]!)}
              submitLabel="Save changes"
              submitting={formBusy}
              serverError={formError}
              onSubmit={(values) => submitEdit(mode.id, values)}
              onCancel={cancelForm}
            />
          ) : mode.kind === "add" ? (
            <TravelRecordForm
              idPrefix="add"
              submitLabel="Add trip"
              submitting={formBusy}
              serverError={formError}
              onSubmit={submitAdd}
              onCancel={cancelForm}
            />
          ) : null}
        </div>
      </Dialog>

      <ConfirmDialog
        open={removeRecord !== null}
        title="Remove this trip?"
        description={
          removeRecord
            ? `${removeRecord.destination_label} (${formatDate(removeRecord.departure_date)} to ${formatDate(removeRecord.return_date)}) will be removed from your travel history.`
            : ""
        }
        confirmLabel="Remove trip"
        busy={removing}
        onConfirm={() => removeRecord && doRemove(removeRecord)}
        onCancel={() => removeId && cancelRemove(removeId)}
      />
    </section>
  );
}
