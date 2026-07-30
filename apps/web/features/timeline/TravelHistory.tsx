"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { useApiClient } from "@/lib/api";

import { CsvImport } from "./CsvImport";
import { TravelRecordForm } from "./TravelRecordForm";
import type { TravelFormValues } from "./TravelRecordForm";
import { buttonStyle, cardStyle, errorTextStyle, linkButtonStyle, secondaryButtonStyle } from "./ui";

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

// A record is trusted only when confirmed AND its dates are exact (the M3B gate); any
// other combination is surfaced as "Uncertain" so unconfirmed records stay visibly
// distinct (§8.4). Status is carried by text + glyph, never colour alone.
function trust(r: Travel): { confirmed: boolean; label: string; detail: string } {
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
  return { confirmed, label: confirmed ? "Confirmed" : "Uncertain", detail };
}

function toBody(values: TravelFormValues) {
  return {
    destination_label: values.destination_label,
    destination_country_code: values.destination_country_code || null,
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
    destination_country_code: r.destination_country_code ?? "",
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
export function TravelHistory({ caseId }: { caseId: string }) {
  const api = useApiClient();
  const [records, setRecords] = useState<Travel[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [mode, setMode] = useState<Mode>({ kind: "none" });
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | undefined>();
  const [removeId, setRemoveId] = useState<string | null>(null);
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

  // Cancelling the form is a user action, so hand focus back rather than dropping it to
  // <body>: flushSync commits the close before we focus the button that regains prominence.
  function cancelForm() {
    flushSync(closeForm);
    document.getElementById("add-trip")?.focus();
  }

  // Opening/closing the inline remove-confirm swaps the focused button out; move focus
  // to its replacement synchronously so a keyboard user is never stranded on <body>.
  function openRemove(id: string) {
    flushSync(() => setRemoveId(id));
    document.getElementById(`confirm-remove-${id}`)?.focus();
  }

  function cancelRemove(id: string) {
    flushSync(() => setRemoveId(null));
    document.getElementById(`remove-${id}`)?.focus();
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
      closeForm();
      load({ notice: "Trip added." });
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
      closeForm();
      load({ notice: "Trip updated." });
      return;
    }
    if (response?.status === 409) {
      setFormError("This trip changed elsewhere. Cancel and reload.");
      return;
    }
    setFormError(response?.status === 422 ? "Please check the dates and try again." : "Something went wrong.");
  }

  async function doRemove(record: Travel) {
    const { data, response } = await api.DELETE(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}",
      {
        params: {
          path: { case_id: caseId, travel_record_id: record.id },
          query: { expected_revision: record.revision },
        },
      },
    );
    setRemoveId(null);
    if (data) {
      load({ notice: "Trip removed." });
      return;
    }
    load({ notice: response?.status === 409 ? "That trip changed elsewhere; reloaded." : "Could not remove the trip." });
  }

  // Sort client-side so the "earliest first" caption is truthful regardless of the
  // endpoint's ordering (the API also sorts, but the caption shouldn't depend on it).
  const sorted = [...records].sort((a, b) => a.departure_date.localeCompare(b.departure_date));

  return (
    <section aria-labelledby="travel-heading" style={cardStyle}>
      <h3 ref={headingRef} tabIndex={-1} id="travel-heading" style={{ margin: 0, fontSize: "var(--cw-text-lg)" }}>
        Travel history
      </h3>
      <p style={{ marginTop: "var(--cw-space-2)", color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        Every period you spent outside the UK. Confirmed and uncertain trips are kept
        distinct; absence calculations arrive in a later milestone.
      </p>

      {/* Polite region for the result of an add / edit / remove / import. */}
      <p role="status" aria-live="polite" style={{ margin: 0, color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        {notice}
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
          {mode.kind === "add" && (
            <div style={{ marginTop: "var(--cw-space-4)" }}>
              <TravelRecordForm
                idPrefix="add"
                submitLabel="Add trip"
                submitting={formBusy}
                serverError={formError}
                onSubmit={submitAdd}
                onCancel={cancelForm}
              />
            </div>
          )}

          {mode.kind === "edit" && (
            <div style={{ marginTop: "var(--cw-space-4)" }}>
              <TravelRecordForm
                idPrefix="edit"
                initial={toForm(records.find((r) => r.id === mode.id) ?? records[0]!)}
                submitLabel="Save changes"
                submitting={formBusy}
                serverError={formError}
                onSubmit={(values) => submitEdit(mode.id, values)}
                onCancel={cancelForm}
              />
            </div>
          )}

          {records.length === 0 ? (
            <p style={{ marginTop: "var(--cw-space-4)" }}>
              No trips recorded yet. Add one below, or import a spreadsheet.
            </p>
          ) : (
            <table style={{ marginTop: "var(--cw-space-4)", borderCollapse: "collapse", width: "100%" }}>
              <caption style={{ textAlign: "left", fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)", marginBottom: "var(--cw-space-2)" }}>
                Your recorded trips, earliest first
              </caption>
              <thead>
                <tr>
                  <th scope="col" style={thStyle}>Destination</th>
                  <th scope="col" style={thStyle}>Departure</th>
                  <th scope="col" style={thStyle}>Return</th>
                  <th scope="col" style={thStyle}>Status</th>
                  <th scope="col" style={thStyle}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => {
                  const t = trust(r);
                  return (
                    <tr key={r.id}>
                      <td style={tdStyle}>
                        {r.destination_label}
                        {r.destination_country_code ? ` (${r.destination_country_code})` : ""}
                      </td>
                      <td style={tdStyle}>{formatDate(r.departure_date)}</td>
                      <td style={tdStyle}>{formatDate(r.return_date)}</td>
                      <td style={tdStyle}>
                        {/* Glyph is decorative; the text carries the status (non-colour). */}
                        <span aria-hidden="true">{t.confirmed ? "✓ " : "● "}</span>
                        <span style={{ fontWeight: "var(--cw-weight-medium)" }}>{t.label}</span>
                        {t.detail && (
                          <span style={{ display: "block", fontSize: "var(--cw-text-xs)", color: "var(--cw-text-muted)" }}>
                            {t.detail}
                          </span>
                        )}
                      </td>
                      <td style={tdStyle}>
                        {removeId === r.id ? (
                          <span role="group" aria-label={`Remove ${r.destination_label}?`} style={{ display: "inline-flex", gap: "var(--cw-space-2)", alignItems: "center" }}>
                            <span>Remove?</span>
                            <button
                              type="button"
                              id={`confirm-remove-${r.id}`}
                              onClick={() => doRemove(r)}
                              style={linkButtonStyle}
                            >
                              Yes
                            </button>
                            <button type="button" onClick={() => cancelRemove(r.id)} style={linkButtonStyle}>
                              No
                            </button>
                          </span>
                        ) : (
                          <span style={{ display: "inline-flex", gap: "var(--cw-space-3)" }}>
                            <button
                              type="button"
                              onClick={() => {
                                setMode({ kind: "edit", id: r.id });
                                setFormError(undefined);
                              }}
                              style={linkButtonStyle}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              id={`remove-${r.id}`}
                              onClick={() => openRemove(r.id)}
                              style={linkButtonStyle}
                            >
                              Remove
                            </button>
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
    </section>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--cw-space-2) var(--cw-space-3)",
  borderBottom: "1px solid var(--cw-border-strong)",
  fontSize: "var(--cw-text-sm)",
};

const tdStyle: React.CSSProperties = {
  padding: "var(--cw-space-2) var(--cw-space-3)",
  borderBottom: "1px solid var(--cw-border)",
  verticalAlign: "top",
};
