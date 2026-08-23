import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";

import { renderWithQuery as render } from "@/test/render";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { ApplicationDateCard } from "./ApplicationDateCard";

const SELECT = "/api/v1/cases/{case_id}/application-dates/select";
const SIMULATE = "/api/v1/cases/{case_id}/application-dates/simulate";
const RECALCULATE = "/api/v1/cases/{case_id}/assessments/recalculate";

function aDate(overrides: Record<string, unknown> = {}) {
  return {
    case_id: "c1",
    application_date: "2027-04-15",
    version_number: 1,
    review_state: "CONFIRMED",
    source: "USER_ENTERED",
    is_current: true,
    revision: 2,
    created_at: "2026-07-30T00:00:00Z",
    ...overrides,
  };
}

function aRequirement(overrides: Record<string, unknown> = {}) {
  return {
    requirement_key: "residence.physical_presence_start_date",
    title: "Presence on the first day",
    group_key: "RESIDENCE",
    display_order: 6,
    changed: {
      conclusion: true,
      summary_code: true,
      summary_parameters: true,
      limitations: false,
      any: true,
    },
    before: {
      conclusion: "NOT_CURRENTLY_SATISFIED",
      currency: "CURRENT",
      summary_code: "PRESENCE_NOT_SUPPORTED",
      summary: null,
      summary_parameters: {},
      limitations: [],
      stale: null,
    },
    after: {
      currency: "PROVISIONAL",
      conclusion: "SUPPORTED",
      summary_code: "PRESENCE_CONFIRMED",
      summary: { code: "PRESENCE_CONFIRMED", parameters: {}, text: "You were in the UK." },
      summary_parameters: {},
      calculation_breakdown: {},
      limitations: [],
      next_actions: [],
    },
    ...overrides,
  };
}

/** The canonical demo comparison: 15 April → 25 April 2027, 439 days → 429. */
function aSimulation(overrides: Record<string, unknown> = {}) {
  return {
    saved: false,
    mode: "PROVISIONAL",
    current_application_date: "2027-04-15",
    candidate_application_date: "2027-04-25",
    windows_before: {
      qualifying_period_start: "2022-04-16",
      qualifying_period_end: "2027-04-15",
      final_year_start: "2026-04-16",
      final_year_end: "2027-04-15",
      presence_anchor: "2022-04-16",
    },
    windows_after: {
      qualifying_period_start: "2022-04-26",
      qualifying_period_end: "2027-04-25",
      final_year_start: "2026-04-26",
      final_year_end: "2027-04-25",
      presence_anchor: "2022-04-26",
    },
    resolving_application_date: null,
    requirements: [
      aRequirement(),
      aRequirement({
        requirement_key: "residence.total_absences",
        title: "Total absences",
        changed: {
          conclusion: false,
          summary_code: false,
          summary_parameters: true,
          limitations: false,
          any: true,
        },
        before: {
          conclusion: "NEAR_THRESHOLD",
          currency: "CURRENT",
          summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
          summary: null,
          summary_parameters: { days: 439 },
          limitations: [],
          stale: null,
        },
        after: {
          currency: "PROVISIONAL",
          conclusion: "NEAR_THRESHOLD",
          summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
          summary: null,
          summary_parameters: { days: 429 },
          calculation_breakdown: {},
          limitations: [],
          next_actions: [],
        },
      }),
      // The noise case: an age parameter republished on every candidate date. It must
      // not be listed as a change.
      aRequirement({
        requirement_key: "route.adult_applicant",
        title: "Adult applicant",
        changed: {
          conclusion: false,
          summary_code: false,
          summary_parameters: true,
          limitations: false,
          any: true,
        },
        before: {
          conclusion: "SUPPORTED",
          currency: "CURRENT",
          summary_code: "ADULT",
          summary: null,
          summary_parameters: { age_years: 39 },
          limitations: [],
          stale: null,
        },
        after: {
          currency: "PROVISIONAL",
          conclusion: "SUPPORTED",
          summary_code: "ADULT",
          summary: null,
          summary_parameters: { age_years: 40 },
          calculation_breakdown: {},
          limitations: [],
          next_actions: [],
        },
      }),
    ],
    ...overrides,
  };
}

async function previewADate(candidate = "2027-04-25") {
  fireEvent.change(await screen.findByLabelText("Application date"), {
    target: { value: candidate },
  });
  fireEvent.click(screen.getByRole("button", { name: /preview this date/i }));
}

describe("ApplicationDateCard", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue({ data: aDate(), error: undefined });
  });

  it("loads the current date and offers a preview rather than a save", async () => {
    render(<ApplicationDateCard caseId="c1" />);
    const input = (await screen.findByLabelText("Application date")) as HTMLInputElement;
    expect(input.value).toBe("2027-04-15");
    expect(screen.getByRole("button", { name: /preview this date/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save/i })).not.toBeInTheDocument();
  });

  it("shows the before and after comparison without saving anything", async () => {
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();

    expect(await screen.findByText(/preview — not saved/i)).toBeInTheDocument();
    expect(screen.getByText("439 days")).toBeInTheDocument();
    expect(screen.getByText("429 days")).toBeInTheDocument();
    // The window moved as a whole, not just the anchor (ADR-0002).
    expect(screen.getByText(/16 April 2022 to 15 April 2027/)).toBeInTheDocument();
    expect(screen.getByText(/26 April 2022 to 25 April 2027/)).toBeInTheDocument();

    // Exactly one request, and it is the simulation. Nothing was selected or recalculated.
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith(SIMULATE, {
      params: { path: { case_id: "c1" } },
      body: { candidate_application_date: "2027-04-25" },
    });
  });

  it("does not invalidate anything when previewing", async () => {
    // The endpoint writes no row, marks nothing stale and reconciles no issue
    // (Domain §10.3), so treating a preview as a write would make every destination
    // refetch to be told what it already knows — and would teach the next reader of this
    // code that a preview is a write. Asserted on the cache, not on the docstring.
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    const { client } = render(<ApplicationDateCard caseId="c1" />);
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await previewADate();

    await screen.findByText(/preview — not saved/i);
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("invalidates the case only once the date is actually saved", async () => {
    post.mockResolvedValueOnce({ data: aSimulation(), error: undefined });
    const { client } = render(<ApplicationDateCard caseId="c1" />);
    await previewADate();
    await screen.findByText(/preview — not saved/i);

    const invalidate = vi.spyOn(client, "invalidateQueries");
    post.mockResolvedValueOnce({ data: aDate({ application_date: "2027-04-25" }) });
    post.mockResolvedValueOnce({ data: { requirements: [{ conclusion: "SUPPORTED" }] } });
    fireEvent.click(screen.getByRole("button", { name: /save 25 April 2027/i }));

    await waitFor(() => expect(invalidate).toHaveBeenCalled());
  });

  it("labels every previewed conclusion as a preview, never as current", async () => {
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();

    await screen.findByText(/preview — not saved/i);
    // The `after` side carries the Preview currency badge; a CURRENT badge is never
    // rendered at all, so "Current" must appear nowhere on this surface.
    expect(screen.getAllByText("Preview").length).toBeGreaterThan(0);
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
  });

  it("does not present a republished parameter as a change", async () => {
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();

    await screen.findByText(/preview — not saved/i);
    expect(screen.getByText("Presence on the first day")).toBeInTheDocument();
    expect(screen.getByText("Total absences")).toBeInTheDocument();
    // `route.adult_applicant` republishes the applicant's age on every candidate date.
    // Listing it would put a change with no meaning beside two with a great deal.
    expect(screen.queryByText("Adult applicant")).not.toBeInTheDocument();
  });

  it("says what the candidate date does not fix", async () => {
    // The failure this catches was found by using the screen, not by reading it: at
    // 20 April the presence check still fails, does not *change*, and so appeared
    // nowhere — leaving a shorter absence total as the only visible result of a move
    // made to fix presence. A preview that shows only improvements is false
    // reassurance (CLAUDE.md §2.7).
    post.mockResolvedValue({
      data: aSimulation({
        candidate_application_date: "2027-04-20",
        resolving_application_date: "2027-04-25",
        requirements: [
          aRequirement({
            changed: {
              conclusion: false,
              summary_code: false,
              summary_parameters: false,
              limitations: false,
              any: false,
            },
            after: {
              currency: "PROVISIONAL",
              conclusion: "NOT_CURRENTLY_SATISFIED",
              summary_code: "PRESENCE_NOT_SUPPORTED",
              summary: {
                code: "PRESENCE_NOT_SUPPORTED",
                parameters: {},
                text: "Your confirmed travel records place you outside the UK on 21 April 2022.",
              },
              summary_parameters: {},
              calculation_breakdown: {},
              limitations: [],
              next_actions: [],
            },
          }),
        ],
      }),
      error: undefined,
    });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate("2027-04-20");

    expect(await screen.findByText(/still not satisfied on this date/i)).toBeInTheDocument();
    expect(screen.getByText("Presence on the first day")).toBeInTheDocument();
    expect(screen.getByText(/place you outside the UK on 21 April 2022/)).toBeInTheDocument();
  });

  it("does not repeat a requirement that already appears as a change", async () => {
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();

    await screen.findByText(/preview — not saved/i);
    // Presence changes here, so it belongs in the changes list and nowhere else.
    expect(screen.getAllByText("Presence on the first day")).toHaveLength(1);
    expect(screen.queryByText(/still not satisfied on this date/i)).not.toBeInTheDocument();
  });

  it("does not offer to save the date the case already holds", async () => {
    // Previewing your current date is a fair question — "where do I stand?" — but it is
    // not a comparison. Rendered as one it read "if you apply on 15 April 2027 instead of
    // 15 April 2027" over two identical windows, and offered a Save that would append a
    // date version and mark every conclusion STALE to record a change that never happened.
    post.mockResolvedValue({
      data: aSimulation({
        candidate_application_date: "2027-04-15",
        current_application_date: "2027-04-15",
        requirements: [],
      }),
      error: undefined,
    });
    render(<ApplicationDateCard caseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: /preview this date/i }));

    expect(
      await screen.findByRole("heading", { name: /your current date/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^save/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^close$/i })).toBeInTheDocument();
    expect(screen.queryByText(/instead of/i)).not.toBeInTheDocument();
    // No before/after pair either: both sides would be the same value.
    expect(screen.queryByText("changed to")).not.toBeInTheDocument();
  });

  it("offers the resolving date when the rules found one", async () => {
    post.mockResolvedValue({
      data: aSimulation({
        candidate_application_date: "2027-04-20",
        resolving_application_date: "2027-04-25",
      }),
      error: undefined,
    });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate("2027-04-20");

    const offer = await screen.findByRole("button", { name: /preview 25 April 2027 instead/i });
    expect(offer).toBeInTheDocument();
    expect(
      screen.getByText(/nearest later date whose first day is clear of confirmed absence/i),
    ).toBeInTheDocument();

    // There is no one-day stepper anywhere on this surface: clearing an absent anchor
    // takes moving past the whole trip covering it (ADR-0002).
    expect(screen.queryByRole("button", { name: /\+ ?1 day|next day|one day/i })).toBeNull();

    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    fireEvent.click(offer);
    await waitFor(() =>
      expect(post).toHaveBeenLastCalledWith(SIMULATE, {
        params: { path: { case_id: "c1" } },
        body: { candidate_application_date: "2027-04-25" },
      }),
    );
  });

  it("saves by selecting the date and then recalculating", async () => {
    post.mockResolvedValueOnce({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();
    await screen.findByText(/preview — not saved/i);

    post.mockResolvedValueOnce({ data: aDate({ application_date: "2027-04-25", revision: 3 }) });
    post.mockResolvedValueOnce({
      data: { requirements: [{ conclusion: "SUPPORTED" }, { conclusion: "NOT_YET_ASSESSED" }] },
    });
    fireEvent.click(screen.getByRole("button", { name: /save 25 April 2027/i }));

    await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
    expect(post).toHaveBeenNthCalledWith(2, SELECT, {
      params: { path: { case_id: "c1" } },
      body: { application_date: "2027-04-25", expected_revision: 2 },
    });
    expect(post).toHaveBeenNthCalledWith(3, RECALCULATE, {
      params: { path: { case_id: "c1" } },
    });
    // The preview closes once the save settles — leaving it up would show an unsaved
    // comparison against a date that is now the saved one.
    await waitFor(() =>
      expect(screen.queryByText(/preview — not saved/i)).not.toBeInTheDocument(),
    );
  });

  it("cancels without touching the case", async () => {
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();
    await screen.findByText(/preview — not saved/i);

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    await waitFor(() =>
      expect(screen.queryByText(/preview — not saved/i)).not.toBeInTheDocument(),
    );
    const input = screen.getByLabelText("Application date") as HTMLInputElement;
    expect(input.value).toBe("2027-04-15");
    expect(input).toHaveFocus();
    expect(post).toHaveBeenCalledTimes(1); // the preview, and nothing else
  });

  it("tells the user their comparison is out of date when the save conflicts", async () => {
    post.mockResolvedValueOnce({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();
    await screen.findByText(/preview — not saved/i);

    post.mockResolvedValueOnce({ data: undefined, response: { status: 409 } });
    fireEvent.click(screen.getByRole("button", { name: /save 25 April 2027/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/changed elsewhere/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/out of date/i);
  });

  it("says the date was saved when only the reassessment fails", async () => {
    post.mockResolvedValueOnce({ data: aSimulation(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();
    await screen.findByText(/preview — not saved/i);

    post.mockResolvedValueOnce({ data: aDate({ application_date: "2027-04-25" }) });
    post.mockResolvedValueOnce({ data: undefined, error: {} });
    fireEvent.click(screen.getByRole("button", { name: /save 25 April 2027/i }));

    // The date landed. Reporting a plain failure would tell the user to redo a change
    // that already happened, and hide that their conclusions are now stale.
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/was saved/i);
    expect(alert).toHaveTextContent(/stale/i);
  });

  it("offers a retry when the preview itself fails", async () => {
    post.mockResolvedValue({ data: undefined, error: {} });
    render(<ApplicationDateCard caseId="c1" />);
    await previewADate();

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn’t work out/i);
    post.mockResolvedValue({ data: aSimulation(), error: undefined });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText(/preview — not saved/i)).toBeInTheDocument();
  });

  it("does not act on a control it has announced as unavailable", async () => {
    // `aria-disabled` rather than `disabled`, because a focused button that becomes
    // `disabled` is blurred by the browser and focus is lost mid-flow. The cost is that
    // the control still fires, so the handler must check `busy` — otherwise assistive
    // technology says "unavailable" and a second mutation goes out anyway.
    let resolvePreview: ((value: unknown) => void) | undefined;
    post.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePreview = resolve;
        }),
    );
    render(<ApplicationDateCard caseId="c1" />);
    const trigger = await screen.findByRole("button", { name: /preview this date/i });

    fireEvent.click(trigger);
    await waitFor(() => expect(trigger).toHaveAttribute("aria-disabled", "true"));
    fireEvent.click(trigger);
    fireEvent.click(trigger);

    expect(post).toHaveBeenCalledTimes(1);
    resolvePreview?.({ data: aSimulation(), error: undefined });
    await screen.findByText(/preview — not saved/i);
  });

  it("announces what the date does not fix, not only what it changes", async () => {
    // The panel says "Still not satisfied on this date"; the announcement said "No
    // conclusion changes". Fixing the screen and leaving the spoken version reassuring
    // would have moved the defect rather than removed it.
    post.mockResolvedValue({
      data: aSimulation({
        candidate_application_date: "2027-04-20",
        requirements: [
          aRequirement({
            changed: {
              conclusion: false,
              summary_code: false,
              summary_parameters: false,
              limitations: false,
              any: false,
            },
            after: {
              currency: "PROVISIONAL",
              conclusion: "NOT_CURRENTLY_SATISFIED",
              summary_code: "PRESENCE_NOT_SUPPORTED",
              summary: null,
              summary_parameters: {},
              calculation_breakdown: {},
              limitations: [],
              next_actions: [],
            },
          }),
        ],
      }),
      error: undefined,
    });
    const { container } = render(<ApplicationDateCard caseId="c1" />);
    await previewADate("2027-04-20");
    await screen.findByText(/still not satisfied on this date/i);

    // `waitFor`, because the announcement lands one render later than the panel: the
    // panel text comes from the preview itself, while the announcement is set by an
    // effect keyed on that preview, so `findByText` above can resolve on the commit
    // *before* the effect has flushed. Asserting synchronously read an empty live region
    // on CI while passing every time locally — the only live-region assertion in this
    // file written without a wait, which is why it was the one that broke.
    const live = container.querySelector('[aria-live="polite"]');
    await waitFor(() => {
      expect(live).toHaveTextContent(/no conclusion changes/i);
      expect(live).toHaveTextContent(/1 requirement is still not satisfied on this date/i);
    });
  });

  it("tells a keyboard user why the alternative date is being offered", async () => {
    post.mockResolvedValue({
      data: aSimulation({
        candidate_application_date: "2027-04-20",
        resolving_application_date: "2027-04-25",
      }),
      error: undefined,
    });
    const { container } = render(<ApplicationDateCard caseId="c1" />);
    await previewADate("2027-04-20");

    const offer = await screen.findByRole("button", { name: /preview 25 April 2027 instead/i });
    const describedBy = offer.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    // Moving control to control never reaches a sibling span, so the reason has to be
    // bound to the button rather than sitting beside it.
    expect(container.querySelector(`#${describedBy}`)).toHaveTextContent(
      /nearest later date whose first day is clear of confirmed absence/i,
    );
  });

  it("shows an error with retry when the date cannot be loaded", async () => {
    get.mockResolvedValue({ data: undefined, error: {} });
    render(<ApplicationDateCard caseId="c1" />);

    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
    get.mockResolvedValue({ data: aDate(), error: undefined });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /preview this date/i })).toBeInTheDocument(),
    );
  });

  it("handles a case with no date chosen yet", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    expect(await screen.findByText(/no date selected yet/i)).toBeInTheDocument();
  });
});
