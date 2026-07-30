import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
const client = { GET: vi.fn(), POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { CsvImport } from "./CsvImport";

function upload(csv: string) {
  const file = new File([csv], "trips.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("Travel history CSV file"), { target: { files: [file] } });
}

describe("CsvImport", () => {
  beforeEach(() => post.mockReset());

  it("imports a clean file after the dry-run check passes", async () => {
    const onImported = vi.fn();
    post
      .mockResolvedValueOnce({ data: { total: 2, valid_count: 2, error_count: 0, all_valid: true, rows: [] } })
      .mockResolvedValueOnce({ data: { imported_count: 2, records: [] } });
    render(<CsvImport caseId="c1" onImported={onImported} />);

    upload("header\nrow\nrow");
    fireEvent.click(await screen.findByRole("button", { name: /import 2 rows/i }));

    await waitFor(() => expect(onImported).toHaveBeenCalledWith(2));
    // First call validates, second commits.
    expect(post.mock.calls[0]![0]).toBe("/api/v1/cases/{case_id}/travel-records/import/validate");
    expect(post.mock.calls[1]![0]).toBe("/api/v1/cases/{case_id}/travel-records/import");
  });

  it("shows the exact failing rows and disables import until fixed", async () => {
    post.mockResolvedValueOnce({
      data: {
        total: 2,
        valid_count: 1,
        error_count: 1,
        all_valid: false,
        rows: [
          { row_number: 2, valid: true, errors: [], value: null },
          {
            row_number: 3,
            valid: false,
            errors: [{ field: "departure_date", code: "DATE_INVALID_FORMAT", message: "expected YYYY-MM-DD" }],
            value: null,
          },
        ],
      },
    });
    render(<CsvImport caseId="c1" onImported={vi.fn()} />);

    upload("header\ngood\nbad");
    // The offending row number and message are shown.
    expect(await screen.findByText(/expected YYYY-MM-DD/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import 1 rows/i })).toBeDisabled();
  });

  it("reports a structurally malformed file", async () => {
    post.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "missing required columns: departure_date" },
      response: { status: 422 },
    });
    render(<CsvImport caseId="c1" onImported={vi.fn()} />);

    upload("wrong,header\nx,y");
    expect(await screen.findByText(/missing required columns/i)).toBeInTheDocument();
  });
});
