import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "@/test/render";

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: del };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { EvidenceDestination } from "./EvidenceDestination";

const CASE_ID = "case-1";
/** The default id `anItem` carries; named because the focus test addresses the row by it. */
const ITEM_ID = "ev-1";

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
    page_count: null,
    pages_read: null,
    character_count: null,
    text_truncated: false,
    can_retry: false,
    proposed_category: null,
    proposed_category_confidence: null,
    proposed_category_reasoning: null,
    analysis_note: null,
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
  del.mockResolvedValue({ data: undefined, error: undefined });
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
    // No extraction has run on this fixture, so the "What we read" column says so rather
    // than answering with a file size — and "yet", because UPLOADED is not terminal and
    // the row would otherwise read "State: Uploaded. What we read: Not read."
    expect(row.getByText("Not read yet")).toBeTruthy();
    expect(row.getByText("booking.pdf")).toBeTruthy();
  });

  it("distinguishes reading a document from checking it against the case", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // The milestone boundary, and it moved in slice 3: text *is* now read, so the old
    // copy ("nothing has read them yet") became false and this test caught it. What must
    // stay true is the distinction the product turns on — reading a document is not
    // checking it, and no figure in the assessment rests on anything but what the user
    // typed.
    expect(await screen.findByText(/does not check anything against your case/)).toBeTruthy();
    expect(screen.getByText(/rests on dates you entered yourself/)).toBeTruthy();
    expect(screen.getByText(/nothing here is checked against your case/)).toBeTruthy();
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

  it("returns focus to the heading when reloading the library succeeds", async () => {
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

describe("what extraction found", () => {
  it("reports pages read, never the text itself", async () => {
    // Full document content stays server-side until M8 has a review surface for it.
    // The screen only has to say "this worked".
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          page_count: 3,
          pages_read: 3,
          character_count: 1200,
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    // "Text read", not "Read": heard as a bare word in a cell, "Read" is a homograph
    // that flips from "this was done" to an instruction.
    expect(row.getByText("Text read")).toBeTruthy();
    expect(row.getByText("3 pages")).toBeTruthy();
  });

  it("says plainly when a document had no text to read", async () => {
    // A scan is a valid document, not a broken one. "Failed" would tell the user to fix
    // a file that is perfectly fine.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({ processing_status: "PARTIALLY_COMPLETED", page_count: 1, character_count: 0 }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("No text found")).toBeTruthy();
    expect(row.getByText(/scan or a photo/)).toBeTruthy();
  });

  it("does not let a bounded read look like a complete one", async () => {
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          page_count: 60,
          pages_read: 40,
          character_count: 9000,
          text_truncated: true,
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText(/60 pages, first 40 read/)).toBeTruthy();
  });

  it("does not invent page arithmetic when the character cap stopped the read", async () => {
    // Every page was opened and the read still stopped early. The first version
    // computed `min(pages, 40)` and rendered "10 pages, first 10 read" — untrue, and
    // reassuring in the wrong direction.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          page_count: 10,
          pages_read: 10,
          character_count: 200_000,
          text_truncated: true,
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("10 pages, partly read")).toBeTruthy();
    expect(row.queryByText(/first 10 read/)).toBeNull();
  });
});

describe("retrying", () => {
  it("offers a retry only where the server says one would do something", async () => {
    // `UNSUPPORTED` is a verdict about the file: the same bytes through the same check
    // reach the same answer. A button that cannot work invites the user to keep pressing.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({ id: "a", processing_status: "FAILED", can_retry: true }),
        anItem({ id: "b", display_name: "Bad file", processing_status: "UNSUPPORTED" }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    await screen.findByRole("row", { name: /Athens booking/ });
    expect(screen.getAllByRole("button", { name: /Read it again/ })).toHaveLength(1);
  });

  it("names which document a retry belongs to", async () => {
    // "Read it again" repeated down a column has no antecedent in a screen reader's
    // control list. Same hidden-suffix pattern as the issue queue's Dismiss.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const button = await screen.findByRole("button", { name: /Read it again/ });
    expect(button.textContent).toMatch(/Athens booking/);
  });

  it("does not show the document moving until the server has agreed", async () => {
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    post.mockImplementation(() => new Promise(() => {}));
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Read it again/ }));

    // Still shows the real state; only the control reports that something was asked for.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Reading again/ })).toBeTruthy(),
    );
    expect(screen.getByText("Failed")).toBeTruthy();
  });
});

describe("focus after a retry", () => {
  it("returns focus to the row rather than dropping it to the body", async () => {
    // Verified in the browser before it was written: pressing "Read it again" moves the
    // document to a non-retryable state, so the button unmounts and takes keyboard focus
    // with it. `document.activeElement` was `<body>`. Third time this codebase has been
    // caught by a control destroyed by the success it reports.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    post.mockResolvedValue({ data: anItem({ processing_status: "VALIDATING" }) });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const button = await screen.findByRole("button", { name: /Read it again/ });
    button.focus();

    // The document is no longer retryable, so the control goes away.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "VALIDATING", can_retry: false })]),
    });
    fireEvent.click(button);

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /Read it again/ })).toBeNull(),
    );
    await waitFor(() => {
      expect(document.activeElement).not.toBe(document.body);
      expect(document.activeElement?.id).toBe(`evidence-row-${ITEM_ID}`);
    });
  });

  it("holds focus on the button while the retry is still in flight", async () => {
    // The counterpart, and the reason focus is armed in onSettled rather than in the click
    // handler: moving it the moment the button is pressed yanks focus mid-press, before
    // there is any outcome to move it for.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    post.mockImplementation(() => new Promise(() => {}));

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const button = await screen.findByRole("button", { name: /Read it again/ });
    button.focus();
    fireEvent.click(button);

    await waitFor(() => expect(button).toHaveAttribute("aria-disabled", "true"));
    expect(document.activeElement).toBe(button);
  });

  it("announces that the document is being read again", async () => {
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    post.mockResolvedValue({ data: anItem({ processing_status: "VALIDATING" }) });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    fireEvent.click(await screen.findByRole("button", { name: /Read it again/ }));

    await waitFor(() =>
      expect(screen.getByText("Reading that document again.")).toBeTruthy(),
    );
  });
});

describe("copy that must hold in every state", () => {
  it("says the same true thing when the case holds no documents", async () => {
    // The trap this catches: copy that asserts a *state* rather than describing what the
    // screen does. "Nothing here has been read yet" became false in slice 3; replacing
    // it with "their text has been read" was false on an empty case. Both were caught in
    // the browser, neither by a test.
    get.mockResolvedValue({ data: aLibrary([]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    await screen.findByTestId("evidence-empty");
    expect(screen.getByText(/nothing here is checked against your case/)).toBeTruthy();
    expect(screen.queryByText(/has been read/)).toBeNull();
  });
});

describe("what the screen says out loud", () => {
  it("reports a refused retry instead of silently reverting", async () => {
    // Not an edge case: PARTIALLY_COMPLETED is retryable and deterministically returns
    // to PARTIALLY_COMPLETED, so "retry a scan, watch it come back, retry again" walks
    // straight into the cooldown. Before this the label flipped back, the row was
    // unchanged, and nothing on the page said why.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "PARTIALLY_COMPLETED", can_retry: true })]),
    });
    post.mockResolvedValue({
      data: undefined,
      error: { code: "EVIDENCE_RETRY_TOO_SOON", retry_after_seconds: 22 },
    });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    fireEvent.click(await screen.findByRole("button", { name: /Read it again/ }));

    await waitFor(() => expect(screen.getByText(/try again in 22 seconds/)).toBeTruthy());
  });

  it("explains a refusal that no amount of waiting fixes", async () => {
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "FAILED", can_retry: true })]),
    });
    post.mockResolvedValue({ data: undefined, error: { code: "EVIDENCE_NOT_RETRYABLE" } });

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    fireEvent.click(await screen.findByRole("button", { name: /Read it again/ }));

    await waitFor(() =>
      expect(screen.getByText(/Uploading a different file may help/)).toBeTruthy(),
    );
  });

  it("announces a document finishing, having announced it starting", async () => {
    // Polling rewrote the State cell every 1.5s with nothing reaching the live region, so
    // a screen-reader user who asked for a re-read was told it started and never told how
    // it ended — the half of the interaction carrying the answer.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "VALIDATING" })]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    await screen.findByRole("row", { name: /Athens booking/ });

    get.mockResolvedValue({
      data: aLibrary([
        anItem({ processing_status: "COMPLETED", page_count: 3, pages_read: 3, character_count: 900 }),
      ]),
    });

    await waitFor(
      () => expect(screen.getByText(/Athens booking: Text read/)).toBeTruthy(),
      { timeout: 4000 },
    );
  });

  it("does not announce documents that were already finished on arrival", async () => {
    // Landing on a page of settled rows is not five things happening.
    get.mockResolvedValue({
      data: aLibrary([anItem({ processing_status: "COMPLETED", page_count: 1, pages_read: 1, character_count: 10 })]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    await screen.findByRole("row", { name: /Athens booking/ });
    expect(screen.queryByText(/Athens booking: Text read/)).toBeNull();
  });

  it("blocks every retry control while one is in flight", async () => {
    // One mutation observer serves all rows, so a second press silently abandoned the
    // first — its button reverted and its outcome was reported nowhere.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({ id: "a", processing_status: "FAILED", can_retry: true }),
        anItem({ id: "b", display_name: "Second doc", processing_status: "FAILED", can_retry: true }),
      ]),
    });
    post.mockImplementation(() => new Promise(() => {}));

    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    const buttons = await screen.findAllByRole("button", { name: /Read it again/ });
    fireEvent.click(buttons[0]!);

    await waitFor(() => {
      for (const button of screen.getAllByRole("button", { name: /Read/ })) {
        expect(button).toHaveAttribute("aria-disabled", "true");
      }
    });
  });

  it("never tells an assistive-technology user something the table contradicts", async () => {
    // The upload announcement said "nothing has read it yet" — corrected in the caption
    // and the page note when reading landed, missed here, and this is the only copy no
    // sighted user ever sees.
    const { container } = renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);
    await screen.findByTestId("evidence-empty");
    const live = container.querySelector('[aria-live="polite"]');
    expect(live?.textContent).not.toMatch(/nothing has read/i);
  });
});

describe("deleting a document", () => {
  it("asks first, and says what deletion does beyond this screen", async () => {
    // The one irreversible action in the library. The dialog has to carry three facts the
    // user cannot get anywhere else: the contents are destroyed, it cannot be undone, and
    // the consequence reaches the assessment — a trip loses its document and the
    // travel-records check needs working out again.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));

    const dialog = within(screen.getByRole("alertdialog"));
    expect(dialog.getByText(/contents destroyed|contents/)).toBeTruthy();
    expect(dialog.getByText(/cannot be undone/)).toBeTruthy();
    expect(dialog.getByText(/no document attached/)).toBeTruthy();
    expect(del).not.toHaveBeenCalled();
  });

  it("deletes on confirmation and announces it", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    del.mockResolvedValue({ data: undefined, error: undefined });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));

    await waitFor(() => expect(screen.getByText("Athens booking deleted.")).toBeTruthy());
    expect(del).toHaveBeenCalledWith(
      "/api/v1/cases/{case_id}/evidence/{evidence_item_id}",
      { params: { path: { case_id: CASE_ID, evidence_item_id: "ev-1" } } },
    );
  });

  it("returns focus to the delete button when the dialog is cancelled", async () => {
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const trigger = await screen.findByRole("button", { name: /Delete Athens booking/ });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: /Cancel/ }));

    await waitFor(() => expect(trigger).toHaveFocus());
    expect(del).not.toHaveBeenCalled();
  });

  it("reports a failed deletion rather than leaving the row to look deleted", async () => {
    // The dialog unmounts either way, so without this the user sees the document still
    // listed and nothing saying why — indistinguishable from a control that did nothing.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    del.mockResolvedValue({ data: undefined, error: { message: "nope" }, response: { status: 500 } });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));

    // `role="alert"`, not merely present-in-the-DOM. The previous assertion was
    // `getByText(/could not be deleted/)`, which passed against the visually-hidden live
    // region — satisfied by exactly the state the comment above calls broken, because
    // jsdom applies no visibility semantics. A sighted user saw nothing.
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/could not be deleted/),
    );
  });

  it("returns focus to the delete control that failed, not to the heading", async () => {
    // The row still exists on the error path — unlike on success — so sending the user to
    // the top of the section makes them Tab past the upload form and the whole table to
    // retry the thing they just attempted.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    del.mockResolvedValue({ data: undefined, error: { message: "nope" }, response: { status: 500 } });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: /Delete Athens booking/ }),
    );
  });

  it("keeps both dialog buttons focusable while the deletion is in flight", async () => {
    // `aria-disabled`, never `disabled`. Disabling the focused button blurs it to <body>,
    // which is outside the panel — so the Tab trap and Escape both stop working, and the
    // user's focus sits behind the backdrop with no indicator (WCAG 2.4.11). jsdom does
    // not model that blur, so this asserts the attribute the rule turns on rather than the
    // symptom it produces.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    del.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    const confirm = screen.getByRole("button", { name: "Delete document" });
    fireEvent.click(confirm);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Deleting…" })).toBeTruthy(),
    );
    const busy = screen.getByRole("button", { name: "Deleting…" });
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(busy.hasAttribute("disabled")).toBe(false);
    expect(busy.getAttribute("aria-disabled")).toBe("true");
    expect(cancel.getAttribute("aria-disabled")).toBe("true");
  });

  it("does not let Cancel pretend to stop a deletion already in flight", async () => {
    // Cancel used to stay live and cancel nothing: the request continued and the document
    // vanished anyway, having told the user they had stopped it.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    del.mockReturnValue(new Promise(() => {}));
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Deleting…" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).not.toBeNull();
  });

  it("names the document in the dialog title, not only in the description", async () => {
    // A screen reader announcing the accessible name without the description would
    // otherwise ask for confirmation of an irreversible action on an unnamed target.
    get.mockResolvedValue({ data: aLibrary([anItem()]) });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));

    expect(screen.getByRole("alertdialog", { name: /Athens booking/ })).toBeTruthy();
  });

  it("does not let the refetched library count overwrite the deletion outcome", async () => {
    // The defect this was written for was found in Chrome, not here: the region held
    // "Athens booking deleted." for **38 milliseconds** before the refetch landed and the
    // count effect replaced it with "No documents yet.". A polite message overwritten that
    // fast is never announced, so the user was told nothing at all.
    //
    // The old tests could not see it because their GET mock returned the same one-item
    // library forever, so the row never disappeared and the count never changed. This one
    // makes the library actually empty on the second read, which is what really happens.
    get
      .mockResolvedValueOnce({ data: aLibrary([anItem()]) })
      .mockResolvedValue({ data: aLibrary([]) });
    del.mockResolvedValue({ data: undefined, error: undefined, response: { status: 204 } });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    fireEvent.click(await screen.findByRole("button", { name: /Delete Athens booking/ }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));

    // Record every value the region takes, not just the final one. Asserting the end
    // state is not enough: the announcement is deliberately deferred past the focus move,
    // so it lands last either way and a final-state assertion stays green with the count
    // effect firing. What the user loses is a *message in the middle*, so the sequence is
    // the thing to assert. Checked by mutation — dropping the guard turns this red.
    const region = document.querySelector('[aria-live="polite"]')!;
    const seen: string[] = [];
    const observer = new MutationObserver(() => {
      const text = region.textContent?.trim() ?? "";
      if (text && seen.at(-1) !== text) seen.push(text);
    });
    observer.observe(region, { childList: true, subtree: true, characterData: true });

    await waitFor(() => expect(region.textContent).toMatch(/Athens booking deleted/));
    await new Promise((resolve) => setTimeout(resolve, 400));
    observer.disconnect();

    expect(seen.some((text) => /Athens booking deleted/.test(text))).toBe(true);
    expect(seen.filter((text) => /No documents yet/.test(text))).toEqual([]);
  });

  it("names which document each delete control belongs to", async () => {
    // A column of bare "Delete" controls is indistinguishable heard in sequence, and this
    // is the one action here that cannot be undone.
    get.mockResolvedValue({
      data: aLibrary([anItem(), anItem({ id: "ev-2", display_name: "Return flight" })]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    expect(await screen.findByRole("button", { name: /Delete Athens booking/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Delete Return flight/ })).toBeTruthy();
  });
});

describe("what the analysis proposed", () => {
  it("says nothing when the analysis agrees with the user", async () => {
    // Deliberately silent. "Analysis agrees" on every row of a twenty-document library
    // is twenty lines a screen-reader user hears in full, and it trains people to skim
    // past the one row where the two differ — which is the only row this is for.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          category: "TRAVEL_SUPPORT",
          proposed_category: "TRAVEL_SUPPORT",
          proposed_category_confidence: 0.98,
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("Travel booking")).toBeTruthy();
    expect(row.queryByText(/Analysis suggests/)).toBeNull();
  });

  it("shows the disagreement without replacing the user's own category", async () => {
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          category: "TRAVEL_SUPPORT",
          proposed_category: "ENGLISH_LANGUAGE",
          proposed_category_confidence: 0.91,
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // Both are present. The user's answer is not corrected, moved or struck through:
    // the model proposes, the person decides.
    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText("Travel booking")).toBeTruthy();
    expect(row.getByText(/Analysis suggests: English language/)).toBeTruthy();
  });

  it("names the two outcomes only the analysis can give", async () => {
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "COMPLETED",
          category: "TRAVEL_SUPPORT",
          proposed_category: "AMBIGUOUS",
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    // Plain English, not the enum name: "AMBIGUOUS" tells a user nothing about what to
    // do, and it is the model's vocabulary rather than theirs.
    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText(/Analysis suggests: Could not tell/)).toBeTruthy();
  });

  it("explains a spent budget rather than blaming the document", async () => {
    // The failure this prevents: telling someone with a perfectly good document to try
    // a different file, when the truth is the daily limit was reached and tomorrow it
    // will work.
    get.mockResolvedValue({
      data: aLibrary([
        anItem({
          processing_status: "PARTIALLY_COMPLETED",
          page_count: 1,
          pages_read: 1,
          character_count: 800,
          analysis_note:
            "Automatic analysis is paused until tomorrow because today's processing limit was reached. Your document was read and stored, and nothing was lost.",
        }),
      ]),
    });
    renderWithQuery(<EvidenceDestination caseId={CASE_ID} />);

    const row = within(await screen.findByRole("row", { name: /Athens booking/ }));
    expect(row.getByText(/paused until tomorrow/)).toBeTruthy();
  });
});
