"use client";

import type { components } from "@cw/api-client";
import { useQuery } from "@tanstack/react-query";
import { type JSX, useState } from "react";

import { errorTextStyle } from "@/components/ui";
import { formatDate } from "@/features/requirements/dates";
import { useApiClient } from "@/lib/api";
import { caseKeys } from "@/lib/queries";

type Export = components["schemas"]["TravelExportResponse"];
type Scope = components["schemas"]["ExportScope"];

function useTravelExport(caseId: string, scope: Scope) {
  const api = useApiClient();
  return useQuery({
    // Under the case key, so a trip added or edited elsewhere refreshes the list.
    queryKey: [...caseKeys.detail(caseId), "travel-export", scope],
    queryFn: async (): Promise<Export> => {
      const { data, error } = await api.GET("/api/v1/cases/{case_id}/travel-records/export", {
        params: { path: { case_id: caseId }, query: { scope } },
      });
      if (error || !data) throw new Error("travel export unavailable");
      return data;
    },
  });
}

/**
 * The travel list to hand over with an application (ADR-0035).
 *
 * Two layers on one page. The **document** is what prints: a title, the period, the table
 * and one line saying whose record it is, black on white, the shape of the list people
 * already upload. The **controls** around it (scope, print, CSV, and the cautions) are for
 * the screen and are dropped by the print stylesheet.
 *
 * Everything the list says comes from the server: which trips are in the period, their
 * order, why one is marked, and every sentence. This lays it out.
 *
 * Nothing here names this product or says "verified". It is the applicant's own record,
 * and a stamp from a tool would suggest a check that never happened.
 */
export function TravelExport({ caseId }: { caseId: string }): JSX.Element {
  const [scope, setScope] = useState<Scope>("WINDOW");
  const { data, status } = useTravelExport(caseId, scope);
  const api = useApiClient();
  const [csvError, setCsvError] = useState(false);

  async function downloadCsv() {
    setCsvError(false);
    // As a blob, not text: decoding to text strips the byte-order mark the server puts
    // first, and without it Excel opens "Côte d'Ivoire" as mojibake. The file saved is the
    // server's bytes, unchanged.
    const { data: file, error } = await api.GET(
      "/api/v1/cases/{case_id}/travel-records/export.csv",
      { params: { path: { case_id: caseId }, query: { scope } }, parseAs: "blob" },
    );
    if (error || !(file instanceof Blob)) {
      setCsvError(true);
      return;
    }
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = `travel-history-${data?.prepared_on ?? "export"}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const hasNotes = data?.trips.some((trip) => trip.markers.length > 0) ?? false;

  return (
    <section className="cw-travel-export" aria-labelledby="travel-export-heading">
      <div className="cw-travel-export__controls cw-no-print">
        <p style={{ margin: 0 }}>
          <a href={`/cases/${caseId}/data`}>
            <span aria-hidden="true">← </span>Case data
          </a>
        </p>
        <p className="cw-case-data__note" style={{ margin: 0 }}>
          Your trips as one list, for when the application form has more trips than it has
          room for. Print it or save it as a PDF, or download it as a spreadsheet.
        </p>

        <fieldset className="cw-travel-export__scope">
          <legend>Which trips</legend>
          <label>
            <input
              type="radio"
              name="scope"
              checked={scope === "WINDOW"}
              onChange={() => setScope("WINDOW")}
            />
            The five years before your application date
          </label>
          <label>
            <input
              type="radio"
              name="scope"
              checked={scope === "ALL"}
              onChange={() => setScope("ALL")}
            />
            Every trip you have recorded
          </label>
        </fieldset>

        {data && data.cautions.length > 0 ? (
          <ul className="cw-travel-export__cautions" aria-label="Before you rely on this list">
            {data.cautions.map((caution) => (
              <li key={caution.code}>{caution.text}</li>
            ))}
          </ul>
        ) : null}

        <div className="cw-travel-export__actions">
          <button
            type="button"
            className="cw-button"
            onClick={() => window.print()}
            disabled={status !== "success"}
          >
            Print or save as PDF
          </button>
          <button
            type="button"
            className="cw-button cw-button--secondary"
            onClick={() => void downloadCsv()}
            disabled={status !== "success"}
          >
            Download CSV
          </button>
        </div>
        {csvError ? (
          <p role="alert" style={errorTextStyle}>
            The CSV could not be downloaded. Try again.
          </p>
        ) : null}
      </div>

      {status === "pending" ? (
        <p role="status" className="cw-no-print">
          Loading your trips…
        </p>
      ) : null}
      {status === "error" ? (
        <p role="alert" style={errorTextStyle} className="cw-no-print">
          Your trips could not be loaded, so there is no list to show.
        </p>
      ) : null}

      {data ? (
        <article className="cw-travel-list">
          <h2 id="travel-export-heading" className="cw-travel-list__title">
            Travel outside the UK
          </h2>
          <p className="cw-travel-list__period">
            {data.period_text ?? "Every trip recorded, in the order taken."}
          </p>

          {data.trips.length === 0 ? (
            <p>No trips in this period.</p>
          ) : (
            // Scrolls sideways at narrow widths, as a data table may (WCAG 1.4.10), so it
            // is focusable and named: a keyboard user has to be able to scroll it too.
            <div
              className="cw-travel-list__scroll"
              tabIndex={0}
              role="region"
              aria-label="Trips, scrolls sideways"
            >
            <table className="cw-travel-list__table">
              <thead>
                <tr>
                  <th scope="col">Country visited</th>
                  <th scope="col">Reason for trip</th>
                  <th scope="col">Departure date</th>
                  <th scope="col">Return date</th>
                  {hasNotes ? <th scope="col">Note</th> : null}
                </tr>
              </thead>
              <tbody>
                {data.trips.map((trip) => (
                  <tr key={trip.travel_record_id}>
                    <th scope="row">{trip.destination_label}</th>
                    <td>{trip.reason ?? ""}</td>
                    <td className="cw-travel-list__date">{formatDate(trip.departure_date)}</td>
                    <td className="cw-travel-list__date">{formatDate(trip.return_date)}</td>
                    {hasNotes ? (
                      <td>{trip.markers.map((marker) => marker.text).join("; ")}</td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}

          <p className="cw-travel-list__prepared">{data.prepared_text}</p>
        </article>
      ) : null}
    </section>
  );
}
