"use client";

import type { components } from "@cw/api-client";
import { useRef, useState } from "react";

import { useApiClient } from "@/lib/api";

import { buttonStyle, errorTextStyle, secondaryButtonStyle } from "./ui";

type Validation = components["schemas"]["ImportValidationResponse"];
type State = "idle" | "checking" | "checked" | "malformed" | "importing" | "error";

const REQUIRED_COLUMNS = "destination_label, departure_date, return_date, date_confidence";

/** Read a file's text via FileReader (works in the browser and jsdom). */
function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

/**
 * CSV travel-history import. Two phases matching the server contract: the chosen file
 * is dry-run validated first (writing nothing) and every row's status is shown; only
 * when all rows are valid is the atomic import enabled — a correct-before-commit loop.
 * A structurally bad file (missing columns / no rows) is reported as a whole-file error.
 */
export function CsvImport({ caseId, onImported }: { caseId: string; onImported: (n: number) => void }) {
  const api = useApiClient();
  const [state, setState] = useState<State>("idle");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [message, setMessage] = useState<string>("");
  const fileRef = useRef<HTMLInputElement>(null);

  function reset() {
    setValidation(null);
    setMessage("");
    setState("idle");
    if (fileRef.current) fileRef.current.value = "";
  }

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    const content = await readText(file);
    setState("checking");
    setValidation(null);
    const { data, error, response } = await api.POST(
      "/api/v1/cases/{case_id}/travel-records/import/validate",
      { params: { path: { case_id: caseId } }, body: { content } },
    );
    if (data) {
      setValidation(data);
      setState("checked");
      return;
    }
    if (response?.status === 422) {
      // Our CsvImportMalformed handler returns { detail: string, code }, which the
      // generated 422 type (FastAPI's default array-shaped detail) doesn't capture.
      const body = error as unknown as { detail?: string } | undefined;
      setMessage(body?.detail ?? "This file can’t be read as a travel history.");
      setState("malformed");
      return;
    }
    setState("error");
  }

  async function doImport() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    const content = await readText(file);
    setState("importing");
    const { data, response } = await api.POST("/api/v1/cases/{case_id}/travel-records/import", {
      params: { path: { case_id: caseId } },
      body: { content },
    });
    if (data) {
      onImported(data.imported_count);
      reset();
      return;
    }
    // The file changed between check and import, or a row is invalid: re-check.
    if (response?.status === 422) {
      setMessage("The file changed since it was checked. Please check it again.");
      setState("malformed");
      return;
    }
    setState("error");
  }

  return (
    <section aria-labelledby="csv-heading" style={{ marginTop: "var(--cw-space-6)" }}>
      <h4 id="csv-heading" style={{ margin: 0, fontSize: "var(--cw-text-base)" }}>
        Import from a spreadsheet
      </h4>
      <p style={{ marginTop: "var(--cw-space-2)", color: "var(--cw-text-muted)", fontSize: "var(--cw-text-sm)" }}>
        Upload a CSV with columns: {REQUIRED_COLUMNS} (and optionally destination_country_code,
        review_state, notes). Nothing is imported until you confirm.
      </p>

      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        aria-label="Travel history CSV file"
        onChange={onFile}
        className="cw-file-input"
        style={{ marginTop: "var(--cw-space-3)", display: "block" }}
      />

      {state === "checking" && (
        <p role="status" style={{ color: "var(--cw-text-muted)", marginTop: "var(--cw-space-3)" }}>
          Checking the file…
        </p>
      )}

      {state === "malformed" && (
        <p role="alert" style={{ marginTop: "var(--cw-space-3)", ...errorTextStyle }}>
          {message}
        </p>
      )}

      {state === "error" && (
        <p role="alert" style={{ marginTop: "var(--cw-space-3)", ...errorTextStyle }}>
          Something went wrong. Please try again.
        </p>
      )}

      {validation && (state === "checked" || state === "importing") && (
        <div style={{ marginTop: "var(--cw-space-4)" }}>
          <p role="status" style={{ margin: 0 }}>
            {validation.all_valid
              ? `All ${validation.total} rows are ready to import.`
              : `${validation.error_count} of ${validation.total} rows need fixing before importing.`}
          </p>

          {!validation.all_valid && (
            <table style={{ marginTop: "var(--cw-space-3)", borderCollapse: "collapse", width: "100%" }}>
              <caption style={{ textAlign: "left", fontSize: "var(--cw-text-sm)", color: "var(--cw-text-muted)", marginBottom: "var(--cw-space-2)" }}>
                Rows that need fixing
              </caption>
              <thead>
                <tr>
                  <th scope="col" style={thStyle}>Row</th>
                  <th scope="col" style={thStyle}>Problem</th>
                </tr>
              </thead>
              <tbody>
                {validation.rows
                  .filter((r) => !r.valid)
                  .map((r) => (
                    <tr key={r.row_number}>
                      <td style={tdStyle}>{r.row_number}</td>
                      <td style={tdStyle}>
                        {r.errors.map((e) => `${e.field}: ${e.message}`).join("; ")}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          )}

          <div style={{ marginTop: "var(--cw-space-4)", display: "flex", gap: "var(--cw-space-3)", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={doImport}
              disabled={!validation.all_valid || state === "importing"}
              style={buttonStyle}
            >
              {state === "importing" ? "Importing…" : `Import ${validation.valid_count} rows`}
            </button>
            <button type="button" onClick={reset} style={secondaryButtonStyle}>
              Cancel
            </button>
          </div>
        </div>
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
  fontSize: "var(--cw-text-sm)",
  verticalAlign: "top",
};
