import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery as render } from "@/test/render";

const get = vi.fn();
const client = { GET: get, POST: vi.fn(), PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { TravelExport } from "./TravelExport";

function anExport(overrides: Record<string, unknown> = {}) {
  return {
    scope: "WINDOW",
    application_date: "2027-04-15",
    period_start: "2022-04-16",
    period_end: "2027-04-15",
    period_text:
      "Trips between 16 April 2022 and 15 April 2027: the five years up to the application date of 15 April 2027.",
    trips: [
      {
        travel_record_id: "t1",
        destination_label: "Greece",
        reason: "Visiting family",
        departure_date: "2022-07-14",
        return_date: "2022-09-07",
        markers: [],
      },
      {
        travel_record_id: "t2",
        destination_label: "Spain",
        reason: null,
        departure_date: "2023-03-10",
        return_date: "2023-03-20",
        markers: [{ code: "ESTIMATED", text: "Dates estimated" }],
      },
    ],
    cautions: [
      {
        code: "DOCUMENTS_AWAITING_REVIEW",
        count: 1,
        text: "1 document is waiting for your review and may hold trips not listed here yet.",
      },
    ],
    prepared_on: "2026-09-24",
    prepared_text: "Prepared from the applicant's own records on 24 September 2026.",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockImplementation((path: string) =>
    Promise.resolve(
      path.endsWith("export.csv")
        ? { data: new Blob(["\ufeffCountry visited\r\n"]), error: undefined }
        : { data: anExport(), error: undefined },
    ),
  );
});

describe("TravelExport", () => {
  it("lays out the list the way people upload it", async () => {
    render(<TravelExport caseId="c1" />);

    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
      "Country visited",
      "Reason for trip",
      "Departure date",
      "Return date",
      "Note",
    ]);
    const greece = within(table).getByRole("row", { name: /Greece/ });
    expect(greece).toHaveTextContent("Visiting family");
    expect(greece).toHaveTextContent("14 July 2022");
    expect(within(table).getByRole("row", { name: /Spain/ })).toHaveTextContent(
      "Dates estimated",
    );
    expect(screen.getByText(/Trips between 16 April 2022/)).toBeInTheDocument();
  });

  it("says whose record it is, and never that anything was verified", async () => {
    const { container } = render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    expect(screen.getByText(/applicant's own records/)).toBeInTheDocument();
    const sheet = container.querySelector(".cw-travel-list")!;
    expect(sheet.textContent).not.toMatch(/verif|certif|workspace|approved/i);
  });

  it("offers no choice of period, since the form asks about one", async () => {
    render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    expect(screen.queryByRole("radio")).toBeNull();
  });

  it("drops the Note column when no trip needs one", async () => {
    get.mockResolvedValue({
      data: anExport({ trips: [anExport().trips[0]] }),
      error: undefined,
    });
    render(<TravelExport caseId="c1" />);
    const table = await screen.findByRole("table");
    expect(within(table).queryByRole("columnheader", { name: "Note" })).toBeNull();
  });

  it("names what to check before relying on the list, on screen only", async () => {
    render(<TravelExport caseId="c1" />);
    const cautions = await screen.findByRole("list", { name: "Before you rely on this list" });
    expect(cautions).toHaveTextContent(/may hold trips not listed here yet/);
    expect(cautions.closest(".cw-no-print")).not.toBeNull();
  });

  it("prints through the browser, which is where the PDF comes from", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Print or save as PDF" }));
    expect(print).toHaveBeenCalled();
  });

  it("prints under the list's own title, never the product's, and puts it back", async () => {
    // The browser prints the page title in its header; the tab's title names the product.
    document.title = "Travel list · Citizenship Workspace";
    render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");

    window.dispatchEvent(new Event("beforeprint"));
    expect(document.title).toBe("Travel outside the UK");
    window.dispatchEvent(new Event("afterprint"));
    expect(document.title).toBe("Travel list · Citizenship Workspace");
  });

  it("restores the title if the page is left mid-print", async () => {
    document.title = "Travel list · Citizenship Workspace";
    const { unmount } = render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    window.dispatchEvent(new Event("beforeprint"));
    unmount();
    expect(document.title).toBe("Travel list · Citizenship Workspace");
  });

  it("keeps a fallback for browsers that print their own header and footer, on screen only", async () => {
    render(<TravelExport caseId="c1" />);
    const hint = await screen.findByText(/turn off/);
    expect(hint).toHaveTextContent("Headers and footers");
    expect(hint.closest(".cw-no-print")).not.toBeNull();
  });

  it("downloads the CSV through the generated client", async () => {
    const createObjectURL = vi.fn(() => "blob:x");
    Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() });
    // jsdom does not implement the navigation a download link's click starts.
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob)));
    expect(click).toHaveBeenCalled();
    expect(get).toHaveBeenCalledWith("/api/v1/cases/{case_id}/travel-records/export.csv", {
      params: { path: { case_id: "c1" } },
      // A blob keeps the byte-order mark that text decoding would strip.
      parseAs: "blob",
    });
  });

  it("says when there are no trips in the period", async () => {
    get.mockResolvedValue({ data: anExport({ trips: [] }), error: undefined });
    render(<TravelExport caseId="c1" />);
    expect(await screen.findByText("No trips in this period.")).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = render(<TravelExport caseId="c1" />);
    await screen.findByRole("table");
    expect(await axe(container)).toHaveNoViolations();
  });
});
