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
    failure_code: null,
    failure_reason: null,
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
    // and the screen must not let a user infer otherwise. Stated once in the caption and
    // once in the page note, not once per row.
    expect(await screen.findByText(/Nothing has read them yet/)).toBeTruthy();
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

  it("says why a document was refused, not only that it was", async () => {
    // "Unsupported" with no reason is a dead end: the user cannot tell whether to
    // re-export the file, try a different one, or give up.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "UNSUPPORTED",
          failure_code: "CONTENT_DOES_NOT_MATCH_TYPE",
          failure_reason: "This file is not a PDF.",
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("Unsupported")).toBeTruthy();
    expect(row.getByText("This file is not a PDF.")).toBeTruthy();
  });

  it("shows a document moving through validation", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem({ processing_status: "VALIDATING" })]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("Validating")).toBeTruthy();
  });

  it("shows an unrecognised state verbatim rather than as something benign", async () => {
    // ANALYSING is in the domain enum but has no token until slice 3.
    get.mockResolvedValue({ data: aLibrary([anItem({ processing_status: "ANALYSING" })]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // A state this build has no token for must not render as "Uploaded". An API/client
    // skew has to be visible, not silently flattened to the reassuring case.
    expect(await screen.findByText("ANALYSING")).toBeTruthy();
    expect(screen.queryByText("Uploaded")).toBeNull();
    // And it says so, rather than leaving a screen-reader user to guess.
    expect(screen.getByText(/state not recognised/)).toBeTruthy();
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
    // `aria-disabled`, not `disabled`: a disabled control loses focus to <body>. So the
    // guard has to be real — pressing it must still do nothing.
    const submit = screen.getByRole("button", { name: "Upload document" });
    expect(submit).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(submit);
    expect(post).not.toHaveBeenCalled();
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
            upload_url: "https://store.example/upload",
            upload_fields: { key: "cases/x/evidence/abc", "Content-Type": "application/pdf" },
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
    expect(url).toBe("https://store.example/upload");
    // A multipart POST, not a PUT: only POST carries the signed policy that holds the
    // size ceiling and the content type.
    expect(init.method).toBe("POST");

    const form = init.body as FormData;
    expect(form.get("key")).toBe("cases/x/evidence/abc");
    expect(form.get("Content-Type")).toBe("application/pdf");
    // The file must be last — S3 ignores anything after it.
    expect([...form.keys()].at(-1)).toBe("file");

    // The presigned signature is the only credential that URL needs. Sending our Clerk
    // bearer token to a third-party host would be a credential leak.
    expect(JSON.stringify(init.headers ?? {})).not.toMatch(/authorization/i);
    // And no Content-Type header: the browser sets the multipart boundary itself.
    expect(init.headers).toBeUndefined();

    vi.unstubAllGlobals();
  });

  it("adds nothing to the library when the upload fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
    post.mockResolvedValue({
      data: {
        upload_url: "https://store.example/upload",
        upload_fields: { key: "cases/x/evidence/abc", "Content-Type": "application/pdf" },
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

describe("keyboard focus and announcements", () => {
  it("keeps focus on the submit button while the upload runs, and says it started", async () => {
    let release: (value: { ok: boolean }) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise((resolve) => (release = resolve))),
    );
    post.mockResolvedValue({
      data: {
        upload_url: "https://store.example/upload",
        upload_fields: { key: "k", "Content-Type": "application/pdf" },
        upload_token: "tok.sig",
        media_type: "application/pdf",
        expires_in_seconds: 60,
      },
    });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const input = (await screen.findByLabelText("Document file")) as HTMLInputElement;
    choose(input, new File(["%PDF-1.7"], "booking.pdf", { type: "application/pdf" }));

    const submit = screen.getByRole("button", { name: "Upload document" });
    submit.focus();
    fireEvent.click(submit);

    // A `disabled` submit blurs to <body> the instant it is disabled, leaving a keyboard
    // user nowhere for the length of the upload — with the label change they can no
    // longer hear, on an element they are no longer on.
    //
    // **jsdom does not reproduce that blur**, so the focus assertion below documents the
    // intent but does not defend it: swapping `aria-disabled` back to `disabled` leaves
    // this test green. The assertion that actually fails on that mutation is the
    // `aria-disabled` attribute check in "refuses an unsupported type…" above. Verified
    // by making the swap. Keep both — this one describes what the user experiences, that
    // one is what catches a regression.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Uploading…" })).toBeTruthy(),
    );
    expect(document.activeElement).toBe(submit);
    expect(screen.getByText(/Uploading booking/)).toBeTruthy();

    release({ ok: true });
    vi.unstubAllGlobals();
  });

  it("returns focus to the heading when a retry succeeds", async () => {
    get.mockResolvedValueOnce({ data: undefined });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const retry = await screen.findByRole("button", { name: "Try again" });
    retry.focus();

    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    fireEvent.click(retry);

    // The alert card and its button unmount on success, taking focus with them. The
    // heading carries tabIndex={-1} precisely so it can catch it.
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { name: "Evidence" }),
      ),
    );
  });

  it("announces what the library holds once it settles", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // `role="status"` mounted with its text already inside does not announce reliably,
    // so both the empty and the populated case go through the always-mounted region.
    await waitFor(() => expect(screen.getByText("1 document.")).toBeTruthy());
  });
});
