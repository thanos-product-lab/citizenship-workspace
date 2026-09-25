import "@testing-library/jest-dom/vitest";

import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "jest-axe";

import { renderWithQuery as render } from "@/test/render";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const client = { GET: get, POST: vi.fn(), PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { RequirementDetail } from "./RequirementDetail";

function anInput(overrides: Record<string, unknown> = {}) {
  return {
    input_kind: "TRAVEL_RECORD_VERSION",
    input_key: null,
    input_version_id: "11111111-1111-1111-1111-111111111111",
    contribution_role: "CONTEXTUAL",
    label: "Trip to Italy",
    value: "4 May 2026 to 10 May 2026",
    detail: "Confirmed · exact dates",
    version_number: 1,
    is_still_current: true,
    is_removed: false,
    counts_as_confirmed: true,
    provenance_kind: "user_confirmed",
    unavailable: false,
    ...overrides,
  };
}

function aDetail(overrides: Record<string, unknown> = {}) {
  return {
    requirement_key: "residence.total_absences",
    title: "Total absences",
    group_key: "RESIDENCE",
    short_description: "No more than 450 days outside the UK across the five-year period.",
    conclusion: "NEAR_THRESHOLD",
    currency: "CURRENT",
    summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
    summary_parameters: {
      days: 439,
      provisional_days: 439,
      threshold: 450,
      trip_count: 12,
      window_start: "2022-04-16",
      window_end: "2027-04-15",
    },
    summary: {
      code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
      parameters: { days: 439, threshold: 450 },
      text: "439 days outside the UK across your five-year qualifying period, from confirmed travel records, against a threshold of 450. That is close to the standard threshold.",
    },
    stale: null,
    calculation_breakdown: {},
    limitations: [],
    next_actions: [],
    facts_used: [
      anInput({
        input_kind: "APPLICATION_DATE_VERSION",
        input_version_id: "22222222-2222-2222-2222-222222222222",
        label: "Proposed application date",
        value: "15 April 2027",
        detail: "Version 1",
        counts_as_confirmed: null,
      }),
    ],
    travel_inputs: [anInput()],
    evidence_inputs: [],
    rule: {
      semantic_version: "1.0.0",
      rule_set: "2026.07.0",
      lifecycle_status: "ACTIVE",
      effective_from: "2026-07-01T00:00:00Z",
      guidance: [{ source: "GUIDE_AN", section: "Absences from the UK" }],
      guidance_version_recorded: false,
    },
    guidance: [{ source: "GUIDE_AN", section: "Absences from the UK" }],
    history: [],
    ...overrides,
  };
}

describe("RequirementDetail", () => {
  beforeEach(() => get.mockReset());

  it("renders every layer of the explanation stack as a real heading", async () => {
    // UI/UX §7.3: the stack is the domain model rendered, and the document outline is the
    // explanation structure, not a set of disclosure widgets.
    //
    // `h3` under the requirement's `h2`. Both moved down one during the release slice,
    // because the case title in the persistent header is the page's `h1` and this was the
    // only destination that added a second. The layers are divisions of the requirement,
    // so nesting them under it is what the outline actually describes.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Total absences", level: 2 });
    for (const layer of [
      "How this was worked out",
      "Answers used",
      "Trips used",
      "Evidence used",
      "Rule used",
      "Limitations",
      "Next action",
    ]) {
      expect(screen.getByRole("heading", { name: layer, level: 3 })).toBeInTheDocument();
    }
  });

  it("puts the answer before the working", async () => {
    // What reduces confidence and what to do sit under the conclusion; the calculation,
    // inputs, evidence and rule follow; history is last. UI/UX §7.2.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Total absences", level: 2 });
    const order = screen
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);
    expect(order).toEqual([
      "Limitations",
      "Next action",
      "How this was worked out",
      "Answers used",
      "Trips used",
      "Evidence used",
      "Rule used",
      "Assessment history",
    ]);
  });

  it("states an empty layer compactly, without the note that framed its content", async () => {
    // Compact, never removed: the heading and the finding stay, and the note that would
    // introduce a list that is not there does not.
    get.mockResolvedValue({ data: aDetail({ facts_used: [] }) });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    const heading = await screen.findByRole("heading", { name: "Answers used", level: 3 });
    const layer = heading.closest("section")!;
    expect(layer).toHaveAttribute("data-empty", "true");
    expect(layer).toHaveTextContent("None.");
    expect(layer).not.toHaveTextContent(/as they were when this result/);

    // A layer with content keeps its note and is not marked empty.
    const rule = screen.getByRole("heading", { name: "Rule used", level: 3 }).closest("section")!;
    expect(rule).not.toHaveAttribute("data-empty");
    expect(rule).toHaveTextContent("The exact version of the rule behind this result.");
  });

  it("renders the server's summary and never composes its own", async () => {
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    expect(
      await screen.findByText(/439 days outside the UK across your five-year qualifying period/),
    ).toBeInTheDocument();
  });

  it("keeps the evidence layer and states that nothing is linked", async () => {
    // Dropping the layer would let a reader assume the question had been satisfied.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Evidence used" });
    expect(screen.getByText(/No documents are attached to these trips/)).toBeInTheDocument();
    expect(screen.getByText(/use the dates you entered/)).toBeInTheDocument();
  });

  it("says how many travel records actually counted", async () => {
    // §5.4: twelve rows read as twelve pieces of corroboration unless the trust gate is
    // stated. One of these two did not count.
    get.mockResolvedValue({
      data: aDetail({
        travel_inputs: [
          anInput(),
          anInput({
            input_version_id: "33333333-3333-3333-3333-333333333333",
            label: "Trip to Greece",
            detail: "Confirmed · estimated dates",
            counts_as_confirmed: false,
            provenance_kind: "unavailable",
          }),
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(
      await screen.findByText(/1 of the 2 trips count/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Did not count towards the confirmed figure/)).toBeInTheDocument();
  });

  it("does not claim a disputed trip was counted, nor that no documents are linked", async () => {
    // The two false sentences this page printed after M8 slice 4 made a *confirmed* trip
    // fail the §6.1 gate. Both came from reading the stored row: it still says CONFIRMED
    // with EXACT dates, because the conflict is derived, not stored (RFC §42).
    get.mockResolvedValue({
      data: aDetail({
        travel_inputs: [
          anInput(),
          anInput({
            input_version_id: "44444444-4444-4444-4444-444444444444",
            label: "Trip to Italy",
            detail: "Confirmed · conflicting dates",
            counts_as_confirmed: false,
          }),
        ],
        evidence_inputs: [
          anInput({
            input_kind: "EVIDENCE_LINK",
            input_version_id: "55555555-5555-5555-5555-555555555555",
            label: "italy_booking_amended_return",
            value: "Attached to your trip to Italy",
            counts_as_confirmed: null,
          }),
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(
      await screen.findByText(/1 of the 2 trips count/),
    ).toBeInTheDocument();
    // Not "All 2 ... were confirmed with exact dates, so all of them counted".
    expect(screen.queryByText(/so all of them counted/)).not.toBeInTheDocument();
    expect(screen.getByText("italy_booking_amended_return")).toBeInTheDocument();
    expect(screen.queryByText(/No documents are attached to these trips/)).not.toBeInTheDocument();
  });

  it("declares the guidance gap rather than filling it", async () => {
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(
      await screen.findByText(/version of this guidance and the date it was retrieved are not recorded/),
    ).toBeInTheDocument();
    // The rule version is exact and is shown.
    expect(screen.getByText("1.0.0")).toBeInTheDocument();
    expect(screen.getByText("2026.07.0")).toBeInTheDocument();
  });

  it("names the input that moved under a stale conclusion", async () => {
    get.mockResolvedValue({
      data: aDetail({
        currency: "STALE",
        stale: {
          reason_code: "TRAVEL_RECORD_CHANGED",
          reason: "Your travel records changed after this was worked out.",
          marked_stale_at: "2026-08-14T11:36:00Z",
        },
        travel_inputs: [anInput({ is_still_current: false })],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(await screen.findByText(/What changed: Trip to Italy/)).toBeInTheDocument();
    expect(screen.getByText(/has not been rechecked/)).toBeInTheDocument();
    expect(
      screen.getByText(/This has been edited since. The value above is what the rule read/),
    ).toBeInTheDocument();
    // The conclusion is preserved, not withdrawn.
    expect(screen.getByText("Near threshold")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("never claims a stale conclusion still stands", async () => {
    get.mockResolvedValue({
      data: aDetail({
        currency: "STALE",
        stale: {
          reason_code: "TRAVEL_RECORD_CHANGED",
          reason: "Your travel records changed after this was worked out.",
          marked_stale_at: "2026-08-14T11:36:00Z",
        },
      }),
    });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );
    await screen.findByText(/has not been rechecked/);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/still stands/i);
    expect(text).not.toMatch(/still (valid|holds|applies|accurate)/i);
  });

  it("shows the calculation with the confirmed figure named as such", async () => {
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    const table = await screen.findByRole("table");
    expect(within(table).getByText("Days outside the UK")).toBeInTheDocument();
    expect(within(table).getByText("from confirmed records only")).toBeInTheDocument();
    expect(within(table).getByText("439 days")).toBeInTheDocument();
    expect(within(table).getByText("450 days")).toBeInTheDocument();
  });

  it("separates unconfirmed days from the confirmed figure in the calculation", async () => {
    // The §5.3 trap: equal figures in the canonical case hide a wrong-field bug. When they
    // differ the table must show the confirmed total and the unconfirmed excess apart.
    get.mockResolvedValue({
      data: aDetail({
        summary_parameters: { days: 439, provisional_days: 452, threshold: 450, trip_count: 13 },
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    const table = await screen.findByRole("table");
    expect(
      within(table).getByText("Additional days unconfirmed records would add"),
    ).toBeInTheDocument();
    expect(within(table).getByText("13 days")).toBeInTheDocument();
    expect(within(table).getByText("not counted towards the figure above")).toBeInTheDocument();
  });

  it("renders limitations and next actions as text, never bare codes", async () => {
    get.mockResolvedValue({
      data: aDetail({
        limitations: [
          {
            code: "UNCONFIRMED_RECORDS_AFFECT_CONCLUSION",
            severity: "REVIEW_REQUIRED",
            parameters: {},
            text: "Your confirmed records total 439 days.",
            affected_input_ids: ["a", "b"],
          },
        ],
        next_actions: [
          {
            code: "SELECT_APPLICATION_DATE",
            parameters: {},
            text: "Consider moving your proposed application date to 25 April 2027.",
            priority: 1,
            blocking: true,
          },
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(await screen.findByText(/Your confirmed records total 439 days/)).toBeInTheDocument();
    expect(
      screen.getByText(/Consider moving your proposed application date to 25 April 2027/),
    ).toBeInTheDocument();
    expect(screen.queryByText("SELECT_APPLICATION_DATE")).not.toBeInTheDocument();
    expect(screen.getByText(/blocks this requirement being satisfied/)).toBeInTheDocument();
  });

  it("renders an unassessed requirement honestly, with no invented explanation", async () => {
    get.mockResolvedValue({
      data: aDetail({
        requirement_key: "referees.first",
        title: "First referee",
        conclusion: "NOT_YET_ASSESSED",
        currency: null,
        summary_code: null,
        summary: null,
        summary_parameters: {},
        facts_used: [],
        travel_inputs: [],
        history: [],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="referees.first" />);

    expect(await screen.findByText(/hasn’t been assessed yet/)).toBeInTheDocument();
    // No calculation, no facts, no limitations invented for it.
    expect(screen.queryByRole("heading", { name: "Answers used" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    // But the rule that would apply is still shown.
    expect(screen.getByRole("heading", { name: "Rule that would apply" })).toBeInTheDocument();
  });

  it("says the window has closed, above the stale notice when both apply", async () => {
    /**
     * A case can be stale *and* past its date, and the two say different things. Stale
     * means the inputs moved and a recalculation settles it. This means the five-year
     * window itself has closed, which no recalculation fixes — so it goes first.
     *
     * The wording must not call the figures wrong. "451 days across that window" stays
     * true of that window; what changed is whether it is still the window the applicant
     * means.
     */
    get.mockResolvedValue({
      data: aDetail({
        application_date: "2026-04-15",
        application_date_has_passed: true,
        currency: "STALE",
        stale: {
          reason_code: "TRAVEL_RECORD_CHANGED",
          reason: "Your travel records changed after this was worked out.",
          marked_stale_at: "2026-08-14T11:36:00Z",
        },
      }),
    });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );

    const notice = await waitFor(() => {
      const found = container.querySelector(".cw-date-passed-notice");
      expect(found).not.toBeNull();
      return found as HTMLElement;
    });
    expect(notice.textContent).toMatch(/15 April 2026/);
    expect(notice.textContent).not.toMatch(/wrong|invalid|out of date/i);

    const stale = container.querySelector(".cw-stale-notice");
    expect(stale).not.toBeNull();
    expect(notice.compareDocumentPosition(stale as Node)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("shows no date notice while the date is still ahead", async () => {
    get.mockResolvedValue({ data: aDetail({ application_date_has_passed: false }) });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );
    await screen.findByRole("heading", { name: "Total absences" });
    expect(container.querySelector(".cw-date-passed-notice")).toBeNull();
  });

  it("shows history with figures so a change is visible", async () => {
    get.mockResolvedValue({
      data: aDetail({
        history: [
          {
            assessment_run_id: "r2",
            conclusion: "NEAR_THRESHOLD",
            currency: "CURRENT",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 440 },
            summary: { code: "X", parameters: {}, text: "440 days outside the UK." },
            created_at: "2026-08-14T11:37:00Z",
          },
          {
            assessment_run_id: "r1",
            conclusion: "NEAR_THRESHOLD",
            currency: "SUPERSEDED",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 439 },
            summary: { code: "X", parameters: {}, text: "439 days outside the UK." },
            created_at: "2026-08-14T11:36:00Z",
          },
        ],
      }),
    });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );

    await screen.findByRole("heading", { name: "Assessment history" });
    // Both runs concluded NEAR_THRESHOLD, so the conclusions alone read as no change.
    // The figures are what make it legible.
    expect(container.querySelector(".cw-change__before")?.textContent).toBe("439 days");
    expect(container.querySelector(".cw-change__after")?.textContent).toBe("440 days");
    expect(screen.getByText("changed to")).toBeInTheDocument();
    expect(screen.getByText("Superseded")).toBeInTheDocument();
  });

  it("names the rule behind each entry, so a version move is not read as a data move", async () => {
    /**
     * A history entry used to render four things — conclusion, currency, summary,
     * timestamp — and none of them said which rule produced it. The block above states
     * the rule for the *displayed* result only, so a reader looking at a superseded
     * figure had no way to find out.
     *
     * The stakes are clearest when the figure moves and the conclusion does not, which is
     * the canonical 439 → 440: with no version on the entries, the reader has exactly one
     * explanation available — the applicant's data changed — and a rule version change is
     * the other one. Here the rule really did move between the runs, and the list has to
     * be able to say so.
     */
    get.mockResolvedValue({
      data: aDetail({
        history: [
          {
            assessment_run_id: "r2",
            conclusion: "NEAR_THRESHOLD",
            currency: "CURRENT",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 440 },
            summary: { code: "X", parameters: {}, text: "440 days outside the UK." },
            created_at: "2026-08-14T11:37:00Z",
            rule_semantic_version: "1.1.0",
            rule_set: "2026.07.0",
          },
          {
            assessment_run_id: "r1",
            conclusion: "NEAR_THRESHOLD",
            currency: "SUPERSEDED",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 439 },
            summary: { code: "X", parameters: {}, text: "439 days outside the UK." },
            created_at: "2026-08-14T11:36:00Z",
            rule_semantic_version: "1.0.0",
            rule_set: "2026.07.0",
          },
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Assessment history" });
    expect(screen.getByText(/Rule 1\.1\.0/)).toBeInTheDocument();
    expect(screen.getByText(/Rule 1\.0\.0/)).toBeInTheDocument();
  });

  it("says nothing about a rule it was not told", async () => {
    // A result that outlived its rule version. The row still renders; it just does not
    // invent a version, because fabricated provenance is the worst defect here.
    get.mockResolvedValue({
      data: aDetail({
        history: [
          {
            assessment_run_id: "r2",
            conclusion: "SUPPORTED",
            currency: "CURRENT",
            summary_code: null,
            summary_parameters: {},
            summary: null,
            created_at: "2026-08-14T11:37:00Z",
          },
          {
            assessment_run_id: "r1",
            conclusion: "SUPPORTED",
            currency: "SUPERSEDED",
            summary_code: null,
            summary_parameters: {},
            summary: null,
            created_at: "2026-08-14T11:36:00Z",
          },
        ],
      }),
    });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );

    await screen.findByRole("heading", { name: "Assessment history" });
    expect(container.querySelector(".cw-history__rule")).toBeNull();
    // Scoped to the list: "Rule used", "Rule version" and "Rule set" are legitimate
    // headings in the block above, which describes the rule behind the displayed result.
    expect(container.querySelector(".cw-history")?.textContent).not.toMatch(/Rule /);
  });

  it("does not manufacture a change when the figure did not move", async () => {
    // A recalculation that confirms the previous answer is not a change. "439 → 439"
    // would invent one.
    get.mockResolvedValue({
      data: aDetail({
        history: [
          {
            assessment_run_id: "r2",
            conclusion: "NEAR_THRESHOLD",
            currency: "CURRENT",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 439 },
            summary: { code: "X", parameters: {}, text: "439 days outside the UK." },
            created_at: "2026-08-14T11:37:00Z",
          },
          {
            assessment_run_id: "r1",
            conclusion: "NEAR_THRESHOLD",
            currency: "SUPERSEDED",
            summary_code: "TOTAL_ABSENCES_NEAR_THRESHOLD",
            summary_parameters: { days: 439 },
            summary: { code: "X", parameters: {}, text: "439 days outside the UK." },
            created_at: "2026-08-14T11:36:00Z",
          },
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    await screen.findByRole("heading", { name: "Assessment history" });
    expect(screen.queryByText("changed to")).not.toBeInTheDocument();
  });

  it("does not strike through the superseded figure", async () => {
    // A superseded figure was correct under the inputs of its run. Strikethrough would
    // read as a correction of something wrong, which is the opposite of the claim that
    // historical results stay inspectable.
    get.mockResolvedValue({
      data: aDetail({
        history: [
          {
            assessment_run_id: "r2",
            conclusion: "NEAR_THRESHOLD",
            currency: "CURRENT",
            summary_code: "X",
            summary_parameters: { days: 440 },
            summary: { code: "X", parameters: {}, text: "440 days." },
            created_at: "2026-08-14T11:37:00Z",
          },
          {
            assessment_run_id: "r1",
            conclusion: "NEAR_THRESHOLD",
            currency: "SUPERSEDED",
            summary_code: "X",
            summary_parameters: { days: 439 },
            summary: { code: "X", parameters: {}, text: "439 days." },
            created_at: "2026-08-14T11:36:00Z",
          },
        ],
      }),
    });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );
    await screen.findByText("changed to");
    expect(container.querySelector("s, del, strike")).toBeNull();
    expect(container.querySelector(".cw-change__before")?.textContent).toBe("439 days");
  });

  it("degrades to the error state when the payload is missing its list fields", async () => {
    // Caught in the browser: an API older than this build answered without `facts_used`
    // and the page threw, blanking the route. During a deploy the two versions coexist,
    // so a schema the client did not expect must degrade rather than crash.
    const withoutFacts: Record<string, unknown> = aDetail();
    delete withoutFacts["facts_used"];
    get.mockResolvedValue({ data: withoutFacts });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn’t load this requirement.");
  });

  it("marks a removed record as removed, not as edited", async () => {
    // Removal is a tombstone: the record keeps pointing at this version, so
    // `is_still_current` stays true and only `is_removed` reveals the deletion. Before
    // this, a deleted trip rendered as a live, confirmed, counting input.
    get.mockResolvedValue({
      data: aDetail({
        currency: "STALE",
        stale: {
          reason_code: "TRAVEL_RECORD_CHANGED",
          reason: "Your travel records changed after this was worked out.",
          marked_stale_at: "2026-08-14T11:36:00Z",
        },
        travel_inputs: [
          anInput({ is_still_current: true, is_removed: true, counts_as_confirmed: false }),
        ],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    expect(await screen.findByText(/This record has been removed since/)).toBeInTheDocument();
    expect(screen.queryByText(/This has been edited since/)).not.toBeInTheDocument();
    expect(screen.getByText(/Did not count towards the confirmed figure/)).toBeInTheDocument();
    // And it is named as the thing that changed.
    expect(screen.getByText(/What changed: Trip to Italy/)).toBeInTheDocument();
  });

  it("does not say there is nothing to do when a limitation is unresolved", async () => {
    // Several evaluators raise limitations without emitting a next action. "Nothing to do"
    // one layer below an unresolved limitation is false reassurance.
    get.mockResolvedValue({
      data: aDetail({
        conclusion: "INCONSISTENT",
        limitations: [
          {
            code: "CONFLICTING_SOURCE_DATES",
            severity: "REVIEW_REQUIRED",
            parameters: {},
            text: "The dates on this trip conflict between sources.",
            affected_input_ids: ["a"],
          },
        ],
        next_actions: [],
      }),
    });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByText(/The dates on this trip conflict between sources/);
    expect(screen.queryByText(/nothing to do for this requirement/)).not.toBeInTheDocument();
    expect(screen.getByText(/The limitations above are still open/)).toBeInTheDocument();
  });

  it("does not point at the Limitations layer when it is empty", async () => {
    // Caught in the browser: a NEAR_THRESHOLD result with no limitations showed
    // "Anything listed under Limitations is still unresolved" directly beneath a
    // Limitations layer reading "No limitations were recorded" — two layers contradicting
    // each other. Not reassuring, but incoherent, which is its own kind of untrustworthy.
    get.mockResolvedValue({ data: aDetail({ conclusion: "NEAR_THRESHOLD", limitations: [] }) });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Next action" });
    expect(screen.getByText("No action is listed for this result.")).toBeInTheDocument();
    expect(screen.queryByText(/Anything listed under Limitations/)).not.toBeInTheDocument();
    // And it still must not claim there is nothing to do.
    expect(screen.queryByText(/nothing to do for this requirement/)).not.toBeInTheDocument();
  });

  it("names the headline figure as confirmed and states the threshold in words", async () => {
    // The message registry commits to always naming the trusted total as confirmed; this
    // is the one figure composed outside it, and a middle dot is skipped by screen readers.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    expect(
      await screen.findByText("439 confirmed days against a threshold of 450"),
    ).toBeInTheDocument();
  });

  it("scopes the travel-record count to what this assessment read", async () => {
    // Under a stale result the user's current records and the run's inputs differ, so
    // "all of your travel records" would be a false claim about the present.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    expect(
      await screen.findByText(/trips were confirmed with exact dates/),
    ).toBeInTheDocument();
  });

  it("keeps the travel layer when no records were read", async () => {
    get.mockResolvedValue({ data: aDetail({ travel_inputs: [] }) });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    await screen.findByRole("heading", { name: "Trips used" });
    expect(within(screen.getByRole("region", { name: "Trips used" })).getByText("None.")).toBeInTheDocument();
  });

  it("404s for an unknown requirement key", async () => {
    get.mockResolvedValue({ data: undefined, response: { status: 404 } });
    render(<RequirementDetail caseId="c1" requirementKey="not.a.requirement" />);
    expect(
      await screen.findByRole("heading", { name: /requirement not found/i }),
    ).toBeInTheDocument();
  });

  it("shows an error state with a retry that refetches", async () => {
    get.mockResolvedValueOnce({ data: undefined, response: { status: 500 } });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn’t load this requirement.");

    get.mockResolvedValueOnce({ data: aDetail() });
    screen.getByRole("button", { name: "Try again" }).click();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Total absences" })).toBeInTheDocument(),
    );
  });

/**
 * The automated floor for this flow (release slice, accessibility pass).
 *
 * axe finds the mechanical failures — an unlabelled control, a broken ARIA reference, a
 * heading level skipped, a contrast pair below ratio. It cannot find the ones this project
 * has actually shipped: a label that told a user to act before the screen to act on
 * existed, a live region overwritten 38ms after it was written, a status distinguished only
 * by hue. Those come from the keyboard and greyscale passes. This stops the mechanical ones
 * reaching them.
 */
  it("has no axe violations", async () => {
    get.mockResolvedValue({ data: aDetail() });
    const { container } = render(
      <RequirementDetail caseId="c1" requirementKey="residence.total_absences" />,
    );
    await screen.findByRole("heading", { name: "Total absences", level: 2 });
    expect(await axe(container)).toHaveNoViolations();
  });
});
