import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "@/test/render";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { EvidenceDestination } from "./EvidenceDestination";

const CASE_ID = "case-1";

/** Pick a file. `fireEvent` is the house convention; `files` needs defining by hand. */
function choose(input: HTMLInputElement, file: File): void {
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  fireEvent.change(input);
}

function anItem(overrides: Record<string, unknown> = {}) {
  return {
    id: "ev-1",
    case_id: CASE_ID,
    category: "TRAVEL_SUPPORT",
    display_name: "Athens booking",
    lifecycle_status: "ACTIVE",
    processing_status: "UPLOADED",
    media_type: "application/pdf",
    size_bytes: 2048,
    original_filename: "booking.pdf",
    uploaded_at: "2026-08-20T10:00:00Z",
    created_at: "2026-08-20T10:00:00Z",
    revision: 1,
    ...overrides,
  };
}

function aLibrary(items: unknown[] = []) {
  return {
    items,
    supported_media_types: ["application/pdf", "image/jpeg", "image/png", "image/heic"],
    max_upload_bytes: 20 * 1024 * 1024,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ data: aLibrary() });
});

describe("EvidenceDestination", () => {
  it("names the documents the case holds and what state each is in", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // Scoped to the row: "Travel booking" is also a category option in the upload form,
    // and asserting on the document is not the same as asserting on the form.
    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("Uploaded")).toBeTruthy();
    expect(row.getByText("Travel booking")).toBeTruthy();
    expect(row.getByText("2 KB")).toBeTruthy();
    expect(row.getByText("booking.pdf")).toBeTruthy();
  });

  it("says plainly that nothing has read the documents yet", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // The whole point of the milestone boundary: a stored document is not a checked one,
    // and the screen must not let a user infer otherwise.
    expect(await screen.findByText(/Stored, and not yet read by anything/)).toBeTruthy();
    expect(screen.getByText(/rests on dates you entered yourself/)).toBeTruthy();
  });

  it("offers no stage the product cannot reach", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    const { container } = renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    await screen.findByRole("row", { name: /Athens booking/ });

    // AWAITING_CONFIRMATION has no producer until M8. Naming it — in a stepper, a
    // "next:" hint, or anywhere else — would promise a stage no document can enter.
    expect(container.textContent).not.toMatch(/awaiting confirmation/i);
    expect(container.querySelector("progress")).toBeNull();
  });

  it("shows an unrecognised state verbatim rather than as something benign", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem({ processing_status: "ANALYSING" })]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // A state this build has no token for must not render as "Uploaded". An API/client
    // skew has to be visible, not silently flattened to the reassuring case.
    expect(await screen.findByText("ANALYSING")).toBeTruthy();
    expect(screen.queryByText("Uploaded")).toBeNull();
  });

  it("distinguishes an empty library from one that could not be loaded", async () => {
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    expect(await screen.findByTestId("evidence-empty")).toBeTruthy();

    get.mockResolvedValue({ data: undefined });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/not a statement about what the case holds/);
    expect(screen.getAllByRole("button", { name: "Try again" }).length).toBeGreaterThan(0);
  });
});

describe("uploading", () => {
  it("refuses an unsupported type before any request is made", async () => {
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const input = (await screen.findByLabelText("Document file")) as HTMLInputElement;

    choose(input, new File(["x"], "notes.txt", { type: "text/plain" }));

    const error = await screen.findByRole("alert");
    expect(error.textContent).toMatch(/not one this product can read/);
    // The courtesy check must not have started an upload: nothing reached the API.
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Upload document" })).toBeDisabled();
  });

  it("binds the file error to the input that caused it", async () => {
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const input = (await screen.findByLabelText("Document file")) as HTMLInputElement;

    choose(input, new File(["x"], "notes.txt", { type: "text/plain" }));

    // Accessibility gate: errors are bound to their field, not floating nearby.
    await waitFor(() => expect(input.getAttribute("aria-invalid")).toBe("true"));
    const describedBy = input.getAttribute("aria-describedby") ?? "";
    expect(describedBy).toContain("upload-file-error");
  });

  it("uploads in three steps and never sends the session token to the object store", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    post.mockImplementation((path: string) => {
      if (path.endsWith("/uploads")) {
        return Promise.resolve({
          data: {
            upload_url: "https://store.example/put/abc",
            upload_token: "tok.sig",
            media_type: "application/pdf",
            expires_in_seconds: 60,
          },
        });
      }
      return Promise.resolve({ data: anItem() });
    });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const input = (await screen.findByLabelText("Document file")) as HTMLInputElement;
    choose(input, new File(["%PDF-1.7"], "booking.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("https://store.example/put/abc");
    expect(init.method).toBe("PUT");
    // The presigned signature is the only credential that URL needs. Sending our Clerk
    // bearer token to a third-party host would be a credential leak.
    expect(JSON.stringify(init.headers)).not.toMatch(/authorization/i);
    // And the content type must be exactly what was signed, or the store refuses it.
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/pdf");

    vi.unstubAllGlobals();
  });

  it("adds nothing to the library when the upload fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    post.mockResolvedValue({
      data: {
        upload_url: "https://store.example/put/abc",
        upload_token: "tok.sig",
        media_type: "application/pdf",
        expires_in_seconds: 60,
      },
    });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const input = (await screen.findByLabelText("Document file")) as HTMLInputElement;
    choose(input, new File(["%PDF-1.7"], "booking.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));

    // Not optimistic: nothing exists server-side until the third call succeeds, so the
    // library must not show a document the case does not hold.
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/nothing has been added to your case/);
    expect(screen.getByTestId("evidence-empty")).toBeTruthy();

    vi.unstubAllGlobals();
  });
});
