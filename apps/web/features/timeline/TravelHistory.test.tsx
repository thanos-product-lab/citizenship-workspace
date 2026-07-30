import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: del };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

// The importer does its own fetching; stub it so this suite tests only the history.
vi.mock("./CsvImport", () => ({ CsvImport: () => <div>csv import stub</div> }));

import { TravelHistory } from "./TravelHistory";

function aRecord(overrides: Record<string, unknown> = {}) {
  return {
    id: "t1",
    case_id: "c1",
    version_number: 1,
    destination_label: "Spain",
    destination_country_code: "ES",
    departure_date: "2022-04-14",
    return_date: "2022-04-26",
    date_confidence: "EXACT",
    review_state: "CONFIRMED",
    entry_source: "MANUAL",
    notes: null,
    lifecycle_status: "ACTIVE",
    revision: 2,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

describe("TravelHistory", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it("shows an empty state when there are no trips", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);
    expect(await screen.findByText(/no trips recorded yet/i)).toBeInTheDocument();
  });

  it("distinguishes confirmed from uncertain trips by text, not colour alone", async () => {
    get.mockResolvedValue({
      data: [
        aRecord({ id: "t1", destination_label: "Spain" }),
        aRecord({ id: "t2", destination_label: "Italy", review_state: "UNCERTAIN" }),
        aRecord({ id: "t3", destination_label: "France", date_confidence: "ESTIMATED" }),
      ],
      error: undefined,
    });
    render(<TravelHistory caseId="c1" />);

    const spain = (await screen.findByText("Spain (ES)")).closest("tr")!;
    expect(within(spain).getByText("Confirmed")).toBeInTheDocument();
    const italy = screen.getByText("Italy (ES)").closest("tr")!;
    expect(within(italy).getByText("Uncertain")).toBeInTheDocument();
    expect(within(italy).getByText("Marked uncertain")).toBeInTheDocument();
    const france = screen.getByText("France (ES)").closest("tr")!;
    expect(within(france).getByText("Uncertain")).toBeInTheDocument();
    expect(within(france).getByText("Estimated dates")).toBeInTheDocument();
  });

  it("adds a trip and announces it", async () => {
    get.mockResolvedValueOnce({ data: [], error: undefined }); // initial empty
    post.mockResolvedValue({ data: aRecord() });
    get.mockResolvedValueOnce({ data: [aRecord()], error: undefined }); // after add
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /add a trip/i }));
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "Spain" } });
    fireEvent.change(screen.getByLabelText("Departure date"), { target: { value: "2022-04-14" } });
    fireEvent.change(screen.getByLabelText("Return date"), { target: { value: "2022-04-26" } });
    fireEvent.click(screen.getByRole("button", { name: /add trip/i }));

    await waitFor(() => expect(screen.getByText("Trip added.")).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith("/api/v1/cases/{case_id}/travel-records", {
      params: { path: { case_id: "c1" } },
      body: expect.objectContaining({ destination_label: "Spain", review_state: "CONFIRMED" }),
    });
  });

  it("rejects a client-side reversed date range before calling the server", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /add a trip/i }));
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "Spain" } });
    fireEvent.change(screen.getByLabelText("Departure date"), { target: { value: "2022-04-26" } });
    fireEvent.change(screen.getByLabelText("Return date"), { target: { value: "2022-04-14" } });
    fireEvent.click(screen.getByRole("button", { name: /add trip/i }));

    expect(await screen.findByText(/return date can’t be before/i)).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it("removes a trip after a confirm step", async () => {
    get.mockResolvedValueOnce({ data: [aRecord()], error: undefined });
    del.mockResolvedValue({ data: aRecord({ lifecycle_status: "REMOVED" }) });
    get.mockResolvedValueOnce({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /remove/i }));
    fireEvent.click(screen.getByRole("button", { name: /^yes$/i }));

    await waitFor(() => expect(screen.getByText("Trip removed.")).toBeInTheDocument());
    expect(del).toHaveBeenCalledWith("/api/v1/cases/{case_id}/travel-records/{travel_record_id}", {
      params: { path: { case_id: "c1", travel_record_id: "t1" }, query: { expected_revision: 2 } },
    });
  });

  it("keeps focus on the remove confirmation and returns it on cancel", async () => {
    get.mockResolvedValue({ data: [aRecord()], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /^remove$/i }));
    // Focus lands on the confirmation, not lost to <body>.
    expect(screen.getByRole("button", { name: /^yes$/i })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: /^no$/i }));
    // Cancelling returns focus to the Remove button that regains prominence.
    expect(screen.getByRole("button", { name: /^remove$/i })).toHaveFocus();
  });

  it("returns focus to Add a trip when the add form is cancelled", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /add a trip/i }));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.getByRole("button", { name: /add a trip/i })).toHaveFocus();
  });

  it("shows an error with retry when the list fails to load", async () => {
    get.mockResolvedValue({ data: undefined, error: {} });
    render(<TravelHistory caseId="c1" />);
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});
