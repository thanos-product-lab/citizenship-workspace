import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";

import { renderWithQuery as render } from "@/test/render";
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

  it("flags only uncertain trips by text, leaving confirmed trips clean", async () => {
    get.mockResolvedValue({
      data: [
        aRecord({ id: "t1", destination_label: "Spain" }),
        aRecord({ id: "t2", destination_label: "Italy", review_state: "UNCERTAIN" }),
        aRecord({ id: "t3", destination_label: "France", date_confidence: "ESTIMATED" }),
      ],
      error: undefined,
    });
    render(<TravelHistory caseId="c1" />);

    // Confirmed is the quiet default: no status flag at all.
    const spain = (await screen.findByRole("cell", { name: /Spain/ })).closest("tr")!;
    expect(within(spain).queryByText("Uncertain")).not.toBeInTheDocument();
    expect(within(spain).queryByText("Confirmed")).not.toBeInTheDocument();
    // Uncertain trips are flagged by text (not colour alone), with the reason.
    const italy = screen.getByRole("cell", { name: /Italy/ }).closest("tr")!;
    expect(within(italy).getByText("Uncertain")).toBeInTheDocument();
    expect(within(italy).getByText("Marked uncertain")).toBeInTheDocument();
    const france = screen.getByRole("cell", { name: /France/ }).closest("tr")!;
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
    // Focus lands on the heading, never dropped to <body> during the reload.
    expect(screen.getByRole("heading", { name: "Travel history" })).toHaveFocus();
    expect(post).toHaveBeenCalledWith("/api/v1/cases/{case_id}/travel-records", {
      params: { path: { case_id: "c1" } },
      // The country code is derived from the label, not entered.
      body: expect.objectContaining({
        destination_label: "Spain",
        destination_country_code: "ES",
        review_state: "CONFIRMED",
      }),
    });
  });

  it("closes the add form when clicking outside it, returning focus to the trigger", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /add a trip/i }));
    // A click on the backdrop (the dialog's overlay parent) dismisses the form.
    const overlay = screen.getByRole("dialog").parentElement!;
    fireEvent.mouseDown(overlay);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add a trip/i })).toHaveFocus();
  });

  it("edits via a prefilled modal and returns focus to Edit on cancel", async () => {
    get.mockResolvedValue({ data: [aRecord()], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /^edit$/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: /edit trip/i })).toBeInTheDocument();
    // The dialog opens prefilled with the existing trip.
    expect((within(dialog).getByLabelText("Destination") as HTMLInputElement).value).toBe("Spain");

    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Focus returns to the row's Edit button, not <body>.
    expect(screen.getByRole("button", { name: /^edit$/i })).toHaveFocus();
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

  it("removes a trip after confirming in the dialog", async () => {
    get.mockResolvedValueOnce({ data: [aRecord()], error: undefined });
    del.mockResolvedValue({ data: aRecord({ lifecycle_status: "REMOVED" }) });
    get.mockResolvedValueOnce({ data: [], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /^remove$/i }));
    // A modal opens, naming the trip and asking to confirm.
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Spain \(14 Apr 2022 to 26 Apr 2022\)/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /remove trip/i }));

    await waitFor(() => expect(screen.getByText("Trip removed.")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Travel history" })).toHaveFocus();
    expect(del).toHaveBeenCalledWith("/api/v1/cases/{case_id}/travel-records/{travel_record_id}", {
      params: { path: { case_id: "c1", travel_record_id: "t1" }, query: { expected_revision: 2 } },
    });
  });

  it("focuses the safe action in the dialog and returns focus to Remove on cancel", async () => {
    get.mockResolvedValue({ data: [aRecord()], error: undefined });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /^remove$/i }));
    // Focus lands on Cancel (the safe default), never the destructive action.
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: /cancel/i })).toHaveFocus();
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    // Cancelling closes the dialog and returns focus to the Remove button.
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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
