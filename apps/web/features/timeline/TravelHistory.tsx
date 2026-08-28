"use client";

import type { components } from "@cw/api-client";
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { useQueryClient } from "@tanstack/react-query";

import { useApiClient } from "@/lib/api";
import { assessmentTouched } from "@/lib/queries";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { countryCodeFor } from "./countries";
import { CsvImport } from "./CsvImport";
import { Dialog } from "@/components/Dialog";
import { TravelRecordForm } from "./TravelRecordForm";
import type { TravelFormValues } from "./TravelRecordForm";
import {
  StatusBadge,
  buttonStyle,
  cardStyle,
  errorTextStyle,
  secondaryButtonStyle,
} from "@/components/ui";

type Travel = components["schemas"]["TravelRecordResponse"];
type Document = components["schemas"]["EvidenceResponse"];
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
  // A counter beside the text, because setting the same string twice is a React state
  // bail-out: no re-render, no DOM mutation, and a polite region announces nothing.
  // Attaching an outbound and a return booking to one trip is the ordinary flow, and it
  // was the second one that went unannounced.
  const [notice, setNotice] = useState<{ text: string; seq: number }>({ text: "", seq: 0 });
  const headingRef = useRef<HTMLHeadingElement>(null);
  // The case's document library, for the attach picker and for naming what is attached.
  // Loaded here rather than derived from the trip rows: those carry ids only, because a
  // document's name belongs to the library and duplicating it onto every trip would make
  // two places to keep in step.
  const [documents, setDocuments] = useState<Document[]>([]);
  const [attachTo, setAttachTo] = useState<string | null>(null);
  const [attachBusy, setAttachBusy] = useState(false);
  const [attachError, setAttachError] = useState<string | undefined>();
  const attachRef = useRef<HTMLSelectElement>(null);

  const load = useCallback(
    (opts?: { notice?: string; keepFocus?: boolean }) => {
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
            setNotice((prev) => ({ text: opts.notice ?? "", seq: prev.seq + 1 }));
            // Attaching and detaching leave focus where the user put it. The add/edit/
            // remove flows move it to the heading because their dialog unmounts and takes
            // focus with it; these do not, and moving it *after* a network round trip
            // yanked a keyboard user back to the top of the section mid-keystroke — out
            // of a table they were working through row by row.
            if (!opts.keepFocus) headingRef.current?.focus();
          }
        });
      return () => {
        active = false;
      };
    },
    [api, caseId],
  );

  useEffect(() => load(), [load]);

  const loadDocuments = useCallback(() => {
    let active = true;
    void api
      .GET("/api/v1/cases/{case_id}/evidence", { params: { path: { case_id: caseId } } })
      .then(({ data }) => {
        // A failure here leaves `documents` empty, which reads as "no documents to
        // attach". That is the same shape as a genuinely empty library and is the least
        // harmful degradation available: the trips and their existing attachments still
        // render, and the attach control simply says there is nothing to pick.
        if (active && Array.isArray(data?.items)) setDocuments(data.items as Document[]);
      });
    return () => {
      active = false;
    };
  }, [api, caseId]);

  useEffect(() => loadDocuments(), [loadDocuments]);

  const documentsById = new Map(documents.map((d) => [d.id, d]));
  // Documents still being read cannot be attached: coverage would settle underneath the
  // user seconds later. The server refuses them too — this only avoids offering a choice
  // that will be rejected.
  const attachable = documents.filter(
    (d) => !["VALIDATING", "EXTRACTING_TEXT", "ANALYSING"].includes(d.processing_status),
  );

  function closeAttach(returnToId: string) {
    flushSync(() => {
      setAttachTo(null);
      setAttachError(undefined);
      setAttachBusy(false);
    });
    document.getElementById(returnToId)?.focus();
  }

  async function submitAttach(recordId: string, evidenceItemId: string) {
    setAttachBusy(true);
    setAttachError(undefined);
    const { data, response } = await api.POST(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}/evidence",
      {
        params: { path: { case_id: caseId, travel_record_id: recordId } },
        body: { evidence_item_id: evidenceItemId },
      },
    );
    setAttachBusy(false);
    if (data) {
      closeAttach(`attach-${recordId}`);
      load({ notice: "Document attached.", keepFocus: true });
      // Attaching stales `residence.travel_consistency` server-side, so the requirement
      // and issue views on screen are now out of date. Same call the trip edits make.
      void assessmentTouched(client, caseId);
      return;
    }
    setAttachError(
      response?.status === 409
        ? "That document is still being read. Try again in a moment."
        : "Something went wrong.",
    );
  }

  async function detach(recordId: string, evidenceItemId: string) {
    const { data, error } = await api.DELETE(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}/evidence/{evidence_item_id}",
      {
        params: {
          path: {
            case_id: caseId,
            travel_record_id: recordId,
            evidence_item_id: evidenceItemId,
          },
        },
      },
    );
    if (data) {
      load({ notice: "Document removed from this trip.", keepFocus: true });
      void assessmentTouched(client, caseId);
      return;
    }
    // Said nothing at all before. A screen-reader user pressed Remove, heard silence, and
    // the document was still listed — indistinguishable from a dead button. The attach
    // path already reported its refusals; the asymmetry was an oversight, not a design.
    if (error) load({ notice: "Could not remove that document. Try again.", keepFocus: true });
  }

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
  const attachRecord = attachTo ? (records.find((r) => r.id === attachTo) ?? null) : null;

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
        {notice.text && (
          <span key={notice.seq}>
            <span aria-hidden="true">✓ </span>
            {notice.text}
          </span>
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
            /*
              Explicit roles throughout. Below 34rem the stylesheet sets `display: block`
              on these elements so each trip reads as a record rather than three squeezed
              columns — and `display: block` strips a table's implicit ARIA roles, which
              would quietly turn this into a pile of divs for assistive technology. At
              desktop width every role below matches the implicit one and changes nothing.
            */
            <div className="cw-trips-wrap">
              <table className="cw-trips" role="table">
                <caption className="cw-trips__caption">
                  Your recorded trips, earliest first
                </caption>
                <thead role="rowgroup">
                  <tr role="row">
                    <th role="columnheader" scope="col">Destination</th>
                    <th role="columnheader" scope="col">Dates</th>
                    <th role="columnheader" scope="col">Documents</th>
                    <th role="columnheader" scope="col" style={{ textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody role="rowgroup">
                  {sorted.map((r) => {
                    const t = trust(r);
                    return (
                      <tr role="row" key={r.id}>
                        {/* A row header, not a cell. Without one nothing supplies the trip
                            name when a screen reader reaches the Actions cell, so a row now
                            reads "Remove Athens booking from your trip to Spain" and then a
                            bare "Remove" — and the less-qualified label is the one that
                            deletes the whole trip. `EvidenceDestination` and
                            `ResidenceTimeline` already do this; this table had diverged. */}
                        <th role="rowheader" scope="row" className="cw-trips__destination">
                          {r.destination_label}
                          {/* Confirmed is the quiet default; only uncertain trips are
                              flagged — the exception is what needs the user's attention. */}
                          {!t.confirmed && (
                            <span className="cw-trips__flag">
                              <StatusBadge
                                colorVar={t.colorVar}
                                surfaceVar={t.surfaceVar}
                                glyph={t.glyph}
                                label={t.label}
                              />
                              {t.detail && (
                                <span className="cw-trips__flag-detail">{t.detail}</span>
                              )}
                            </span>
                          )}
                        </th>
                        <td role="cell" className="cw-trips__dates">
                          <div>{formatDate(r.departure_date)}</div>
                          <div className="cw-trips__return">to {formatDate(r.return_date)}</div>
                        </td>
                        <td role="cell" className="cw-trips__documents">
                          {/* Support state, per §11.8 ("a travel record without evidence
                              must expose its support state"). Attached documents are
                              named; nothing attached says so in words.

                              No badge and no colour. A tick beside an attached document
                              would read as "checked", and nothing has read it — the link
                              is the user's assertion, not a verdict (ADR-0021). "None
                              attached" is a statement of fact, not a warning, so it is
                              styled as ordinary muted text rather than as a problem. */}
                          {r.supporting_evidence_item_ids.length === 0 ? (
                            <span className="cw-trips__no-documents">None attached</span>
                          ) : (
                            // `role="list"` because `list-style: none` strips list
                            // semantics in Safari/VoiceOver, and "list, 2 items" is worth
                            // hearing when a trip holds several.
                            <ul className="cw-trips__document-list" role="list">
                              {r.supporting_evidence_item_ids.map((id, index) => {
                                // The library carries the names; the trip carries only ids.
                                // If the library did not load, fall back to a *positional*
                                // label — two documents both named "this document" would be
                                // two identical accessible names on two different
                                // destructive controls, which is the ambiguity the hidden
                                // name exists to prevent.
                                const named = documentsById.get(id)?.display_name;
                                const label =
                                  named ??
                                  `document ${index + 1} of ${r.supporting_evidence_item_ids.length}`;
                                return (
                                <li key={id}>
                                  <span>{named ?? "A document"}</span>
                                  <button
                                    type="button"
                                    className="cw-action cw-action--muted"
                                    onClick={() => void detach(r.id, id)}
                                  >
                                    {/* Names the document, so a screen-reader user
                                        hearing three of these in one row can tell them
                                        apart. The visible word stays "Remove". */}
                                    <span aria-hidden="true">Remove</span>
                                    <span className="cw-visually-hidden">
                                      Remove {label} from your trip to {r.destination_label}
                                    </span>
                                  </button>
                                </li>
                                );
                              })}
                            </ul>
                          )}
                          {attachable.length > 0 && (
                            <button
                              type="button"
                              id={`attach-${r.id}`}
                              className="cw-action"
                              onClick={() => {
                                setAttachTo(r.id);
                                setAttachError(undefined);
                              }}
                            >
                              <span aria-hidden="true">Attach</span>
                              <span className="cw-visually-hidden">
                                Attach a document to your trip to {r.destination_label}
                              </span>
                            </button>
                          )}
                        </td>
                        <td role="cell" className="cw-trips__actions">
                          <span>
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

      <Dialog
        open={attachRecord !== null}
        labelledBy="attach-heading"
        describedBy="attach-note"
        initialFocusRef={attachRef}
        onDismiss={() => attachRecord && closeAttach(`attach-${attachRecord.id}`)}
      >
        {attachRecord && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const chosen = attachRef.current?.value;
              if (chosen) void submitAttach(attachRecord.id, chosen);
            }}
          >
            <h3 id="attach-heading" style={{ margin: "0 0 0.5rem" }}>
              Attach a document to {attachRecord.destination_label}
            </h3>
            {/* Says what attaching does *and* what it does not. Without the second
                sentence a user could reasonably read the tick beside their trip as the
                product having checked the document against it — which nothing has done,
                and which is the false reassurance this whole product is built against. */}
            <p id="attach-note" className="cw-case-data__note" style={{ marginTop: 0 }}>
              This records that the document belongs with this trip. Nothing reads it, and
              your absence totals still come from the dates you entered.
            </p>
            <label htmlFor="attach-select" style={{ display: "block", marginBottom: "0.25rem" }}>
              Document
            </label>
            <select
              id="attach-select"
              ref={attachRef}
              defaultValue={attachable[0]?.id}
              aria-describedby={attachError ? "attach-error" : "attach-note"}
              aria-invalid={attachError ? true : undefined}
              // The refusal is about the *chosen option*, so it clears when the choice
              // changes. Left standing, it would keep describing a selection the user has
              // already moved on from.
              onChange={() => setAttachError(undefined)}
              style={{ width: "100%", padding: "0.5rem" }}
            >
              {attachable.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.display_name}
                </option>
              ))}
            </select>
            {attachError && (
              // Bound to the select, not floated beside it. A banner is announced once and
              // then gone: a user returning to the combo box afterwards heard only the
              // options again, with nothing saying which choice had been refused.
              <p id="attach-error" role="alert" style={errorTextStyle}>
                {attachError}
              </p>
            )}
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
              {/* `aria-disabled`, never `disabled`: disabling the focused button moves
                  focus to <body>, and on the refusal path nothing puts it back — the user
                  is left outside the dialog, outside its Tab trap, with an alert they
                  cannot reach. The same rule is already written down in `globals.css`.
                  jsdom does not model this, which is why the tests were green. */}
              <button
                type="submit"
                style={buttonStyle}
                aria-disabled={attachBusy}
                onClick={(event) => {
                  if (attachBusy) event.preventDefault();
                }}
              >
                {attachBusy ? "Attaching…" : "Attach document"}
              </button>
              <button
                type="button"
                style={secondaryButtonStyle}
                onClick={() => closeAttach(`attach-${attachRecord.id}`)}
              >
                Cancel
              </button>
            </div>
          </form>
        )}
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
