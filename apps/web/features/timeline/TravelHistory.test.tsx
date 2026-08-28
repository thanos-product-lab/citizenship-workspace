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
    supporting_evidence_item_ids: [],
    revision: 2,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

/**
 * Route GET by path rather than by call order.
 *
 * The component loads two things — the trips and the case's document library — so
 * `mockResolvedValueOnce` chains silently mis-deliver: the library's request eats the
 * response queued for the trips reload, and the test fails complaining about a notice
 * that never rendered. Routing by path makes each test say what it means, and survives
 * the component gaining another read.
 */
function mockGet({
  trips = [],
  documents = [],
  tripsError = false,
}: {
  trips?: unknown[];
  documents?: unknown[];
  tripsError?: boolean;
} = {}) {
  get.mockImplementation((path: string) => {
    if (path.endsWith("/evidence")) {
      return Promise.resolve({ data: { items: documents }, error: undefined });
    }
    if (tripsError) return Promise.resolve({ data: undefined, error: { message: "nope" } });
    return Promise.resolve({ data: trips, error: undefined });
  });
}

function aDocument(overrides: Record<string, unknown> = {}) {
  return {
    id: "ev-1",
    case_id: "c1",
    category: "TRAVEL_SUPPORT",
    display_name: "Athens booking",
    lifecycle_status: "ACTIVE",
    processing_status: "COMPLETED",
    media_type: "application/pdf",
    size_bytes: 2048,
    original_filename: "booking.pdf",
    can_retry: false,
    uploaded_at: "2026-08-20T10:00:00Z",
    created_at: "2026-08-20T10:00:00Z",
    revision: 1,
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
    // A rowheader, not a cell: the destination names the row, so the trip's own Edit and
    // Remove are not heard as bare verbs in an unnamed row.
    const spain = (await screen.findByRole("rowheader", { name: /Spain/ })).closest("tr")!;
    expect(within(spain).queryByText("Uncertain")).not.toBeInTheDocument();
    expect(within(spain).queryByText("Confirmed")).not.toBeInTheDocument();
    // Uncertain trips are flagged by text (not colour alone), with the reason.
    const italy = screen.getByRole("rowheader", { name: /Italy/ }).closest("tr")!;
    expect(within(italy).getByText("Uncertain")).toBeInTheDocument();
    expect(within(italy).getByText("Marked uncertain")).toBeInTheDocument();
    const france = screen.getByRole("rowheader", { name: /France/ }).closest("tr")!;
    expect(within(france).getByText("Uncertain")).toBeInTheDocument();
    expect(within(france).getByText("Estimated dates")).toBeInTheDocument();
  });

  it("adds a trip and announces it", async () => {
    // The reload after the POST returns the added trip; the library stays empty. Routed
    // by path, so the two reads cannot be delivered to each other.
    let trips: unknown[] = [];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [] }, error: undefined }
          : { data: trips, error: undefined },
      ),
    );
    post.mockImplementation(() => {
      trips = [aRecord()];
      return Promise.resolve({ data: aRecord() });
    });
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
    let trips: unknown[] = [aRecord()];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [] }, error: undefined }
          : { data: trips, error: undefined },
      ),
    );
    del.mockImplementation(() => {
      trips = [];
      return Promise.resolve({ data: aRecord({ lifecycle_status: "REMOVED" }) });
    });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /^remove$/i }));
    // A modal opens, naming the trip and asking to confirm.
    const dialog = screen.getByRole("alertdialog");
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
    const dialog = screen.getByRole("alertdialog");
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

  describe("the table stays a table when it reflows", () => {
    // Below 34rem the stylesheet sets `display: block` on these elements so each trip
    // reads as a record rather than three squeezed columns. That is the well-known flaw in
    // the pattern: `display: block` strips a table's implicit ARIA roles, silently turning
    // it into a pile of divs for assistive technology. The markup carries explicit roles
    // to survive it, and these assert they are present — jsdom applies no stylesheet, so
    // the roles are the only part of the mechanism a unit test can see. The layout itself
    // is checked in the browser.
    async function renderOneTrip() {
      get.mockResolvedValue({ data: [aRecord()], error: undefined });
      const result = render(<TravelHistory caseId="c1" />);
      await screen.findByRole("table");
      return result;
    }

    it("exposes the table, its rows and its cells explicitly", async () => {
      await renderOneTrip();
      const table = screen.getByRole("table");
      // Header row plus one trip.
      expect(within(table).getAllByRole("row")).toHaveLength(2);
      expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
        "Destination",
        "Dates",
        "Documents",
        "Actions",
      ]);
      // Three cells plus the row header, which is the destination.
      expect(within(table).getAllByRole("cell")).toHaveLength(3);
      expect(within(table).getAllByRole("rowheader")).toHaveLength(1);
    });

    it("keeps the column headers reachable, rather than removing them from the tree", async () => {
      // The header row is visually hidden at narrow widths, not `display: none`, so each
      // cell keeps its column header. Removing the row would leave a screen-reader user
      // with three unlabelled cells per trip.
      await renderOneTrip();
      expect(screen.getByRole("columnheader", { name: "Destination" })).toBeInTheDocument();
    });

    it("keeps one set of controls per trip, so focus restoration resolves the right one", async () => {
      // A second copy of the markup for narrow widths was rejected partly for this: the
      // edit and remove dialogs restore focus by getElementById, which returns whichever
      // copy comes first in the DOM — frequently the hidden one, where focus() does
      // nothing at all.
      await renderOneTrip();
      expect(screen.getAllByRole("button", { name: "Edit" })).toHaveLength(1);
      expect(document.querySelectorAll("#edit-t1")).toHaveLength(1);
      expect(document.querySelectorAll("#remove-t1")).toHaveLength(1);
    });

    it("names the table for anyone listing tables on the page", async () => {
      await renderOneTrip();
      expect(screen.getByRole("table", { name: /recorded trips, earliest first/i })).toBeInTheDocument();
    });
  });

  it("shows an error with retry when the list fails to load", async () => {
    get.mockResolvedValue({ data: undefined, error: {} });
    render(<TravelHistory caseId="c1" />);
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("documents attached to a trip", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it("says plainly when a trip has no document, without calling it a problem", async () => {
    // §11.8: a trip without evidence "must expose its support state". Stated as a fact,
    // not flagged — people take trips they have no paperwork for, and no figure moves
    // either way. A warning badge here would invent a defect.
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    render(<TravelHistory caseId="c1" />);

    const row = within(await screen.findByRole("row", { name: /Spain/ }));
    expect(row.getByText("None attached")).toBeInTheDocument();
    expect(row.queryByText(/missing|required|warning/i)).toBeNull();
  });

  it("names the attached document rather than ticking the trip", async () => {
    // No badge and no tick, deliberately. A tick would read as "checked", and nothing has
    // read this document — the link is the user's assertion, not a verdict (ADR-0021).
    mockGet({
      trips: [aRecord({ supporting_evidence_item_ids: ["ev-1"] })],
      documents: [aDocument()],
    });
    render(<TravelHistory caseId="c1" />);

    const row = within(await screen.findByRole("row", { name: /Spain/ }));
    expect(row.getByText("Athens booking")).toBeInTheDocument();
    expect(row.queryByText("None attached")).toBeNull();
  });

  it("still names a trip's support state when the library has not loaded", async () => {
    // The library carries the names; the trip carries only ids. If the library request
    // fails the row must still say a document is attached rather than silently reading as
    // unevidenced, which would be a false statement about the user's own case.
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: undefined, error: { message: "nope" } }
          : { data: [aRecord({ supporting_evidence_item_ids: ["ev-1"] })], error: undefined },
      ),
    );
    render(<TravelHistory caseId="c1" />);

    const row = within(await screen.findByRole("row", { name: /Spain/ }));
    expect(row.getByText("A document")).toBeInTheDocument();
    expect(row.queryByText("None attached")).toBeNull();
  });

  it("offers no attach control when the case holds no documents", async () => {
    // Nothing to pick from, so the button would open a dialog with an empty list. The
    // Evidence destination is where documents arrive; this screen does not duplicate it.
    mockGet({ trips: [aRecord()], documents: [] });
    render(<TravelHistory caseId="c1" />);

    await screen.findByRole("row", { name: /Spain/ });
    expect(screen.queryByRole("button", { name: /Attach a document/ })).toBeNull();
  });

  it("does not offer a document that is still being read", async () => {
    // Coverage would settle underneath the user seconds later. The server refuses it too;
    // this only avoids offering a choice that will be rejected.
    mockGet({
      trips: [aRecord()],
      documents: [aDocument({ id: "ev-2", processing_status: "EXTRACTING_TEXT" })],
    });
    render(<TravelHistory caseId="c1" />);

    await screen.findByRole("row", { name: /Spain/ });
    expect(screen.queryByRole("button", { name: /Attach a document/ })).toBeNull();
  });

  it("attaches a document and announces it", async () => {
    let trips: unknown[] = [aRecord()];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [aDocument()] }, error: undefined }
          : { data: trips, error: undefined },
      ),
    );
    post.mockImplementation(() => {
      trips = [aRecord({ supporting_evidence_item_ids: ["ev-1"] })];
      return Promise.resolve({ data: trips[0] });
    });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    fireEvent.click(screen.getByRole("button", { name: "Attach document" }));

    await waitFor(() => expect(screen.getByText("Document attached.")).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith(
      "/api/v1/cases/{case_id}/travel-records/{travel_record_id}/evidence",
      { params: { path: { case_id: "c1", travel_record_id: "t1" } }, body: { evidence_item_id: "ev-1" } },
    );
  });

  it("tells the user what attaching does not do", async () => {
    // The one sentence that stops a support column reading as verification. Without it a
    // user could reasonably take an attached document as the product having checked it
    // against the trip — which nothing has done.
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    render(<TravelHistory caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByText(/Nothing reads it/)).toBeInTheDocument();
    expect(dialog.getByText(/dates you entered/)).toBeInTheDocument();
  });

  it("returns focus to the attach button when the dialog is cancelled", async () => {
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    render(<TravelHistory caseId="c1" />);

    const trigger = await screen.findByRole("button", { name: /Attach a document/ });
    fireEvent.click(trigger);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("detaches a document and announces it", async () => {
    let trips: unknown[] = [aRecord({ supporting_evidence_item_ids: ["ev-1"] })];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [aDocument()] }, error: undefined }
          : { data: trips, error: undefined },
      ),
    );
    del.mockImplementation(() => {
      trips = [aRecord()];
      return Promise.resolve({ data: trips[0] });
    });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Remove Athens booking from your trip to Spain/ }),
    );

    await waitFor(() =>
      expect(screen.getByText("Document removed from this trip.")).toBeInTheDocument(),
    );
  });

  it("names which document each remove control belongs to", async () => {
    // Two documents on one trip means two buttons reading "Remove". Heard in sequence with
    // no context they are indistinguishable, and the row already has its own Remove for
    // the trip itself.
    mockGet({
      trips: [aRecord({ supporting_evidence_item_ids: ["ev-1", "ev-2"] })],
      documents: [aDocument(), aDocument({ id: "ev-2", display_name: "Return flight" })],
    });
    render(<TravelHistory caseId="c1" />);

    await screen.findByRole("row", { name: /Spain/ });
    expect(
      screen.getByRole("button", { name: /Remove Athens booking from your trip to Spain/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Remove Return flight from your trip to Spain/ }),
    ).toBeInTheDocument();
    // And the trip's own Remove is still distinct from both.
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });

  it("reports a refusal rather than silently doing nothing", async () => {
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    post.mockResolvedValue({ data: undefined, response: { status: 409 } });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    fireEvent.click(screen.getByRole("button", { name: "Attach document" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/still being read/),
    );
  });
});

describe("what the documents column says out loud", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    del.mockReset();
  });

  it("reports a failed detach instead of silently leaving the document there", async () => {
    // Was completely silent: the response's error was never even destructured. A
    // screen-reader user pressed Remove, heard nothing, and the document was still
    // listed — indistinguishable from a dead button. The attach path already reported
    // its refusals, so the asymmetry was an oversight rather than a design.
    mockGet({
      trips: [aRecord({ supporting_evidence_item_ids: ["ev-1"] })],
      documents: [aDocument()],
    });
    del.mockResolvedValue({ data: undefined, error: { message: "nope" } });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Remove Athens booking from your trip to Spain/ }),
    );

    await waitFor(() =>
      expect(screen.getByText(/Could not remove that document/)).toBeInTheDocument(),
    );
  });

  it("announces the second attach as well as the first", async () => {
    // `setNotice` with the same string twice is a React state bail-out: no re-render, no
    // DOM mutation, and a polite region announces nothing. Attaching an outbound and a
    // return booking to one trip is the ordinary flow, and it was the second that went
    // unannounced.
    let trips: unknown[] = [aRecord()];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [aDocument(), aDocument({ id: "ev-2", display_name: "Return flight" })] } }
          : { data: trips, error: undefined },
      ),
    );
    post.mockImplementation(() => {
      trips = [aRecord({ supporting_evidence_item_ids: ["ev-1"] })];
      return Promise.resolve({ data: trips[0] });
    });

    const { container } = render(<TravelHistory caseId="c1" />);
    const live = container.querySelector('[aria-live="polite"]')!;
    const seen: string[] = [];
    new MutationObserver(() => seen.push(live.textContent ?? "")).observe(live, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    for (let attempt = 0; attempt < 2; attempt += 1) {
      fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
      fireEvent.click(screen.getByRole("button", { name: "Attach document" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    }

    // Two announcements, not one collapsed into a no-op.
    await waitFor(() =>
      expect(seen.filter((t) => t.includes("Document attached.")).length).toBeGreaterThan(1),
    );
  });

  it("keeps the submit button focusable while the attach is in flight", async () => {
    // `disabled` on the focused button moves focus to <body>, and on the refusal path
    // nothing puts it back — the user ends up outside the dialog and outside its Tab
    // trap, with an alert they cannot reach. jsdom does not model that, so this asserts
    // the attribute the rule turns on rather than the focus behaviour it prevents.
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    post.mockImplementation(() => new Promise(() => {}));

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    const submit = screen.getByRole("button", { name: "Attach document" });
    fireEvent.click(submit);

    await waitFor(() => expect(submit).toHaveAttribute("aria-disabled", "true"));
    expect(submit).not.toBeDisabled();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("binds an attach refusal to the field it is about", async () => {
    // A floated banner is announced once and then gone: a user returning to the combo box
    // heard only the options again, with nothing saying which choice had been refused.
    mockGet({ trips: [aRecord()], documents: [aDocument()] });
    post.mockResolvedValue({ data: undefined, response: { status: 409 } });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    fireEvent.click(screen.getByRole("button", { name: "Attach document" }));

    const select = await screen.findByLabelText("Document");
    await waitFor(() => expect(select).toHaveAttribute("aria-invalid", "true"));
    expect(select).toHaveAccessibleDescription(/still being read/);

    // Choosing again clears it: the refusal was about the option, not the form.
    fireEvent.change(select, { target: { value: "ev-1" } });
    await waitFor(() => expect(select).not.toHaveAttribute("aria-invalid"));
  });

  it("leaves focus where the user put it after attaching", async () => {
    // The add/edit/remove flows move focus to the heading because their dialog unmounts
    // and takes focus with it. These do not — and moving it after a network round trip
    // yanked a keyboard user back to the top of the section mid-keystroke.
    let trips: unknown[] = [aRecord()];
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: { items: [aDocument()] }, error: undefined }
          : { data: trips, error: undefined },
      ),
    );
    post.mockImplementation(() => {
      trips = [aRecord({ supporting_evidence_item_ids: ["ev-1"] })];
      return Promise.resolve({ data: trips[0] });
    });

    render(<TravelHistory caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /Attach a document/ }));
    fireEvent.click(screen.getByRole("button", { name: "Attach document" }));

    await waitFor(() => expect(screen.getByText("Document attached.")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Travel history" })).not.toHaveFocus();
  });

  it("gives two unnamed documents distinguishable remove controls", async () => {
    // The library carries the names; the trip carries only ids. With the library
    // unavailable, a shared fallback would put two identical accessible names on two
    // different destructive controls — the exact ambiguity the hidden name exists for.
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/evidence")
          ? { data: undefined, error: { message: "nope" } }
          : {
              data: [aRecord({ supporting_evidence_item_ids: ["ev-1", "ev-2"] })],
              error: undefined,
            },
      ),
    );

    render(<TravelHistory caseId="c1" />);
    await screen.findByRole("rowheader", { name: /Spain/ });
    const names = screen
      .getAllByRole("button", { name: /Remove document/ })
      .map((b) => b.getAttribute("aria-label") ?? b.textContent);

    expect(new Set(names).size).toBe(2);
  });

  it("names the trip on the row so a bare Remove is not the most destructive control", async () => {
    // Heard in sequence a row read "Remove Athens booking from your trip to Spain" and
    // then a bare "Remove" — and the less-qualified label deletes the whole trip. A row
    // header supplies the missing context.
    mockGet({
      trips: [aRecord({ supporting_evidence_item_ids: ["ev-1"] })],
      documents: [aDocument()],
    });
    render(<TravelHistory caseId="c1" />);

    const header = await screen.findByRole("rowheader", { name: /Spain/ });
    expect(header.tagName).toBe("TH");
    expect(header).toHaveAttribute("scope", "row");
  });
});
