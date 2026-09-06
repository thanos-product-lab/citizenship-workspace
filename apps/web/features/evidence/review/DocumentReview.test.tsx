import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery } from "@/test/render";

const get = vi.fn();
const post = vi.fn();
const client = {
  GET: get,
  POST: post,
  PUT: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
};
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { DocumentReview } from "./DocumentReview";

const CASE_ID = "case-1";
const ITEM_ID = "ev-1";

/** The date the demo booking actually states, and the one the model misread it as. */
const DOCUMENT_SAYS = "11 May 2026";
const MODEL_READ = "10 May 2026";

function aClaim(overrides: Record<string, unknown> = {}) {
  return {
    id: "claim-1",
    evidence_item_id: ITEM_ID,
    claim_type: "travel.return_date",
    journey_index: 0,
    value_schema_version: "date.v1",
    // Null, because the API withholds a pending high-risk proposal. The fixture says so
    // explicitly rather than omitting the key: this null is the guarantee under test.
    proposed_value: null,
    normalised_value: null,
    requires_blind_entry: true,
    model_confidence: null,
    source_locator: null,
    status: "PENDING_REVIEW",
    created_at: "2026-09-05T10:00:00Z",
    decision: null,
    ...overrides,
  };
}

function aTextClaim(overrides: Record<string, unknown> = {}) {
  return aClaim({
    id: "claim-2",
    claim_type: "travel.booking_reference",
    value_schema_version: "text.v1",
    proposed_value: "SKY-7P2QMN",
    normalised_value: "SKY-7P2QMN",
    requires_blind_entry: false,
    ...overrides,
  });
}

/** Route the three GETs this screen makes by path. */
function serve({
  claims = [aClaim()],
  preview = {
    url: "https://store.example/doc.pdf?sig=x",
    expires_in_seconds: 900,
  } as { url: string; expires_in_seconds: number } | null,
  text = {
    content: "Return 11 May 2026",
    page_count: 1,
    pages_read: 1,
    character_count: 18,
  },
  claimsStatus = 200,
  textStatus = 200,
}: Record<string, unknown> = {}) {
  get.mockImplementation((path: string) => {
    if (path.endsWith("/claims")) {
      return Promise.resolve({
        data: claimsStatus === 200 ? { items: claims } : undefined,
        response: { status: claimsStatus },
      });
    }
    if (path.endsWith("/content")) {
      return Promise.resolve({
        data: preview ?? undefined,
        response: { status: 200 },
      });
    }
    if (path.endsWith("/text")) {
      return Promise.resolve({
        data: textStatus === 200 ? text : undefined,
        response: { status: textStatus },
      });
    }
    return Promise.resolve({ data: undefined, response: { status: 404 } });
  });
}

function render() {
  return renderWithQuery(
    <DocumentReview
      caseId={CASE_ID}
      evidenceItemId={ITEM_ID}
      documentName="Athens booking"
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  serve();
});

describe("blind confirmation", () => {
  it("renders an empty box for a date and shows the proposal nowhere on the panel", async () => {
    // **Mutation-table row 5, and the plan's one open uncertainty written as an
    // assertion.** The risk blind entry exists to remove is a person confirming what the
    // machine said instead of what the page says — and the way that creeps back is not a
    // pre-filled input but *any* element on screen carrying the value, which someone then
    // types out of. So this checks the whole rendered panel, not just the control.
    const { container } = render();

    const input = await screen.findByLabelText(
      /Return date, as the document writes it/,
    );
    expect(input).toHaveValue("");
    // React writes a `value` attribute on a controlled input even when it is empty, so
    // the assertion is that it is empty rather than that it is absent.
    expect(input.getAttribute("value") ?? "").toBe("");
    expect(container.textContent).not.toMatch(/\d{1,2} \w+ 20\d\d/);
    expect(container.textContent).not.toMatch(/20\d\d-\d\d-\d\d/);
  });

  it("refuses to render a blind proposal even when handed one", async () => {
    // **The assertion that actually tests this component**, and the one the first version
    // of this file was missing. Every other fixture here has `proposed_value: null`,
    // because that is what the API sends for a pending high-risk claim — which meant the
    // test passed with the input pre-filled *and* with the proposal printed beside it.
    // Two mutations, both green. The test was checking the server's guarantee, which the
    // server already tests.
    //
    // So this hands the component a value the API would never send and requires it to
    // ignore it. Defence in depth is only depth if each layer holds on its own: the wire
    // withholds it, and the screen would not show it if the wire ever stopped.
    serve({
      claims: [
        aClaim({ proposed_value: MODEL_READ, normalised_value: "2026-05-10" }),
      ],
    });
    const { container } = render();

    const input = await screen.findByLabelText(
      /Return date, as the document writes it/,
    );
    expect(input).toHaveValue("");
    expect(container.textContent).not.toContain(MODEL_READ);
    expect(container.textContent).not.toContain("2026-05-10");
  });

  it("uses a text input, so an ambiguous date reaches the server intact", async () => {
    // `type="date"` would impose a locale format and resolve `03/04/2025` silently in the
    // browser — the ambiguity the whole design exists to preserve, thrown away before
    // `parse_entered_date` ever sees it. The most deliberate line in the component, and
    // the one a future tidy-up is most likely to "fix".
    render();

    const input = await screen.findByLabelText(
      /Return date, as the document writes it/,
    );
    expect(input).toHaveAttribute("type", "text");
  });

  it("sends only what the person typed, and never asserts which decision it was", async () => {
    // The wire half of the same guarantee. There is no field in the request for "I am
    // confirming" — the server compares the entry against the claim it already holds and
    // works out CONFIRM or CORRECT. A client that could say which would be a client that
    // could say it without looking.
    post.mockResolvedValue({
      data: {
        claim_id: "claim-1",
        claim_status: "CORRECTED",
        decision: "CORRECT",
        review_mode: "BLIND_ENTRY",
        value: "2026-05-11",
      },
    });
    render();

    fireEvent.change(
      await screen.findByLabelText(/Return date, as the document writes it/),
      {
        target: { value: DOCUMENT_SAYS },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    const [, options] = post.mock.calls[0]!;
    expect(options.body.entered_value).toBe(DOCUMENT_SAYS);
    expect(options.body.decision).toBeNull();
  });

  it("says out loud whether that was a confirmation or a correction", async () => {
    // The two outcomes are different information, not different styling. A user who typed
    // what they read and hears "corrected" has just learned the model read the document
    // differently — which is the single most useful thing this screen can tell them, and
    // it is carried only by a badge for anyone who can see one.
    post.mockResolvedValue({
      data: {
        claim_id: "claim-1",
        claim_status: "CORRECTED",
        decision: "CORRECT",
        review_mode: "BLIND_ENTRY",
        value: "2026-05-11",
      },
    });
    render();

    fireEvent.change(
      await screen.findByLabelText(/Return date, as the document writes it/),
      {
        target: { value: DOCUMENT_SAYS },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(screen.getByText(/corrected to 2026-05-11/i).textContent).toMatch(
        /yours is what was recorded/i,
      ),
    );
  });

  it("shows what the model had read once the correction is recorded", async () => {
    // MVP §8.11: correcting preserves the original proposal. The record keeps it either
    // way; this is whether the person can *see* that theirs won. Only reachable after the
    // decision — the API withholds the proposal until then, which is the test above.
    serve({
      claims: [
        aClaim({
          status: "CORRECTED",
          proposed_value: MODEL_READ,
          decision: {
            decision: "CORRECT",
            review_mode: "BLIND_ENTRY",
            reason_code: null,
            value: "2026-05-11",
            reviewed_by: "user_a",
            reviewed_at: "2026-09-06T09:00:00Z",
          },
        }),
      ],
    });
    render();

    expect(await screen.findByText(MODEL_READ)).toBeTruthy();
    // Twice: once as the value now recorded, once as the "after" half of the before/after
    // pair that shows the correction. Both are wanted.
    expect(screen.getAllByText("2026-05-11").length).toBe(2);
    expect(screen.getByText("Corrected")).toBeTruthy();
    // And no control to decide it again: `OPEN_STATUSES` is PENDING_REVIEW alone, so an
    // offer to re-decide is an offer the server refuses.
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});

describe("a field that is not high risk", () => {
  it("shows the proposal and offers confirm as well as correct", async () => {
    // RFC §41.4 spends the friction where a wrong value changes a conclusion, and not
    // where it does not. A booking reference is not worth retyping.
    serve({ claims: [aTextClaim()] });
    render();

    expect(await screen.findByText("SKY-7P2QMN")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Correct" })).toBeTruthy();
    expect(screen.queryByLabelText(/as the document writes it/)).toBeNull();
  });

  it("states the decision, because here the client is the one that knows it", async () => {
    serve({ claims: [aTextClaim()] });
    post.mockResolvedValue({
      data: {
        claim_id: "claim-2",
        claim_status: "CONFIRMED",
        decision: "CONFIRM",
        review_mode: "PREFILLED",
        value: "SKY-7P2QMN",
      },
    });
    render();

    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0]![1].body.decision).toBe("CONFIRM");
  });

  it("seeds a correction with the proposal, which a blind field never does", async () => {
    // Safe here and only here: the user has explicitly said they want to change this
    // value, and starting from what was read saves retyping a reference number. The blind
    // path has no equivalent branch — there is nothing to seed it from.
    serve({ claims: [aTextClaim()] });
    render();

    fireEvent.click(await screen.findByRole("button", { name: "Correct" }));

    expect(screen.getByLabelText(/Booking reference, corrected/)).toHaveValue(
      "SKY-7P2QMN",
    );
  });
});

describe("when the server refuses", () => {
  it("binds an unreadable date to the input and keeps what was typed", async () => {
    // `03/04/2025` typed by a person is exactly as ambiguous as one printed on a booking,
    // and the server refuses both by the same rule. Clearing the box on refusal would make
    // the user retype a value they had read correctly out of a document.
    post.mockResolvedValue({
      error: {
        code: "UNREADABLE_ENTERED_VALUE",
        detail: "that date could be read more than one way.",
      },
      response: { status: 422 },
    });
    render();

    const input = await screen.findByLabelText(
      /Return date, as the document writes it/,
    );
    fireEvent.change(input, { target: { value: "03/04/2025" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const error = await screen.findByRole("alert");
    expect(error.textContent).toMatch(/more than one way/);
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toContain("error");
    expect(input).toHaveValue("03/04/2025");
  });

  it("stops offering to decide a claim someone else already decided", async () => {
    // Two tabs. The second review is refused by the server — `OPEN_STATUSES` is
    // PENDING_REVIEW alone — and the field must show the decision that won rather than
    // inviting the user to overwrite a fact that already exists.
    post.mockResolvedValue({
      error: {
        code: "CLAIM_ALREADY_REVIEWED",
        detail: "this claim has already been reviewed",
      },
      response: { status: 409 },
    });
    render();

    fireEvent.change(
      await screen.findByLabelText(/Return date, as the document writes it/),
      {
        target: { value: DOCUMENT_SAYS },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(
        /already been reviewed/,
      ),
    );
    // Refetched, so the field can show what actually happened rather than staying open.
    await waitFor(() => {
      const claimCalls = get.mock.calls.filter(([path]: [string]) =>
        path.endsWith("/claims"),
      );
      expect(claimCalls.length).toBeGreaterThan(1);
    });
  });
});

describe("rejecting a value", () => {
  it("asks why, and sends the reason", async () => {
    // RFC §10 wants "why was this wrong" answerable across a corpus rather than one claim
    // at a time. A rejection with no reason tells a later evaluation nothing.
    post.mockResolvedValue({
      data: {
        claim_id: "claim-1",
        claim_status: "REJECTED",
        decision: "REJECT",
        review_mode: "BLIND_ENTRY",
        value: null,
      },
    });
    render();

    fireEvent.click(
      await screen.findByRole("button", { name: "This is wrong" }),
    );
    fireEvent.change(screen.getByLabelText("Why is it wrong?"), {
      target: { value: "VALUE_NOT_PRESENT" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Reject this value" }));

    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0]![1].body.decision).toBe("REJECT");
    expect(post.mock.calls[0]![1].body.reason_code).toBe("VALUE_NOT_PRESENT");
  });
});

describe("the two ways to read the document", () => {
  it("embeds the document with a named frame", async () => {
    render();

    const frame = await screen.findByTitle(
      /Athens booking — the document as uploaded/,
    );
    expect(frame).toHaveAttribute("src", "https://store.example/doc.pdf?sig=x");
  });

  it("does not fetch the text until someone asks for it", async () => {
    // The only response in the product that carries a document's words. A tab nobody
    // opened should not pull one over the wire.
    render();
    await screen.findByRole("button", { name: "Text" });
    expect(
      get.mock.calls.some(([path]: [string]) => path.endsWith("/text")),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Text" }));

    await waitFor(() =>
      expect(
        get.mock.calls.some(([path]: [string]) => path.endsWith("/text")),
      ).toBe(true),
    );
    expect(await screen.findByText(/Return 11 May 2026/)).toBeTruthy();
  });

  it("says a partial reading is partial", async () => {
    // A text panel that silently stopped at page 5 would have someone confirming values
    // from a document they have not seen the whole of.
    serve({
      text: {
        content: "page one",
        page_count: 9,
        pages_read: 3,
        character_count: 8,
      },
    });
    render();

    fireEvent.click(await screen.findByRole("button", { name: "Text" }));

    expect(
      await screen.findByText(/Only the first 3 of 9 pages were read/),
    ).toBeTruthy();
  });

  it("says plainly when there is no text rather than showing a blank panel", async () => {
    serve({ textStatus: 404 });
    render();

    fireEvent.click(await screen.findByRole("button", { name: "Text" }));

    expect(
      await screen.findByText(/this looks like a scan or a photo/i),
    ).toBeTruthy();
  });

  it("keeps the fields usable when the document cannot be opened", async () => {
    // A failed preview must never block the review: the fields are the work, and the
    // person can still read their own document however they got it here.
    serve({ preview: null });
    render();

    expect(
      await screen.findByLabelText(/Return date, as the document writes it/),
    ).toBeTruthy();
    expect(screen.getByText(/could not be opened just now/)).toBeTruthy();
  });
});

describe("what the screen says about itself", () => {
  it("counts what is still outstanding, not what exists", async () => {
    serve({
      claims: [
        aClaim(),
        aTextClaim({
          status: "CONFIRMED",
          decision: {
            decision: "CONFIRM",
            review_mode: "PREFILLED",
            reason_code: null,
            value: "SKY-7P2QMN",
            reviewed_by: "user_a",
            reviewed_at: "2026-09-06T09:00:00Z",
          },
        }),
      ],
    });
    render();

    expect(
      await screen.findByText("1 of 2 values still need your decision."),
    ).toBeTruthy();
  });

  it("groups fields by journey only when there is more than one", async () => {
    // A two-leg booking proposes the same field twice; ungrouped, the user sees "Return
    // date" twice with nothing to tell them apart. A single-journey booking has nothing to
    // disambiguate, and "Journey 1" alone implies a Journey 2 to go looking for.
    render();
    await screen.findByLabelText(/as the document writes it/);
    expect(screen.queryByText("Journey 1")).toBeNull();

    serve({ claims: [aClaim(), aClaim({ id: "claim-3", journey_index: 1 })] });
    render();

    expect(await screen.findByText("Journey 1")).toBeTruthy();
    expect(screen.getByText("Journey 2")).toBeTruthy();
  });

  it("distinguishes a document that is gone from one with nothing to decide", async () => {
    // An empty list reads as "nothing needs your decision", which is a true sentence about
    // the wrong thing when the document has been deleted.
    serve({ claimsStatus: 404 });
    render();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/no longer in your case/);
    expect(
      screen.getByRole("link", { name: /Back to your documents/ }),
    ).toBeTruthy();
  });

  it("says nothing is outstanding when every field is decided", async () => {
    serve({
      claims: [
        aTextClaim({
          status: "CONFIRMED",
          decision: {
            decision: "CONFIRM",
            review_mode: "PREFILLED",
            reason_code: null,
            value: "SKY-7P2QMN",
            reviewed_by: "user_a",
            reviewed_at: "2026-09-06T09:00:00Z",
          },
        }),
      ],
    });
    render();

    expect(
      await screen.findByText("All 1 values have been decided."),
    ).toBeTruthy();
  });

  it("separates a failed load from an empty document", async () => {
    get.mockImplementation((path: string) => {
      if (path.endsWith("/claims")) return Promise.reject(new Error("network"));
      return Promise.resolve({ data: undefined, response: { status: 200 } });
    });
    render();

    const alert = await within(await screen.findByRole("alert")).findByText(
      /not a statement about your document/,
    );
    expect(alert).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
