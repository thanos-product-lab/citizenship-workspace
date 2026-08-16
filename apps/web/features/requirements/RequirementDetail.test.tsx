import "@testing-library/jest-dom/vitest";

import { screen, waitFor, within } from "@testing-library/react";

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
    // explanation structure — not a set of disclosure widgets.
    get.mockResolvedValue({ data: aDetail() });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Total absences", level: 1 });
    for (const layer of [
      "Why this assessment was made",
      "Facts used",
      "Travel records used",
      "Evidence used",
      "Rule used",
      "Limitations",
      "Next action",
    ]) {
      expect(screen.getByRole("heading", { name: layer, level: 2 })).toBeInTheDocument();
    }
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
    expect(screen.getByText(/No documents are linked to these records/)).toBeInTheDocument();
    expect(screen.getByText(/dates you entered yourself/)).toBeInTheDocument();
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
      await screen.findByText(/1 of the 2 travel records this assessment read were confirmed/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Did not count towards the confirmed figure/)).toBeInTheDocument();
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
    expect(screen.queryByRole("heading", { name: "Facts used" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    // But the rule that would apply is still shown.
    expect(screen.getByRole("heading", { name: "Rule that would apply" })).toBeInTheDocument();
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
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Assessment history" });
    expect(screen.getByText("440 days outside the UK.")).toBeInTheDocument();
    expect(screen.getByText("439 days outside the UK.")).toBeInTheDocument();
    // Two identical conclusions — the figures are what make the change legible.
    expect(screen.getByText("Superseded")).toBeInTheDocument();
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
    expect(screen.getByText(/Anything listed under Limitations is still unresolved/)).toBeInTheDocument();
  });

  it("does not point at the Limitations layer when it is empty", async () => {
    // Caught in the browser: a NEAR_THRESHOLD result with no limitations showed
    // "Anything listed under Limitations is still unresolved" directly beneath a
    // Limitations layer reading "No limitations were recorded" — two layers contradicting
    // each other. Not reassuring, but incoherent, which is its own kind of untrustworthy.
    get.mockResolvedValue({ data: aDetail({ conclusion: "NEAR_THRESHOLD", limitations: [] }) });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);

    await screen.findByRole("heading", { name: "Next action" });
    expect(screen.getByText("No next action has been recorded for this result.")).toBeInTheDocument();
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
      await screen.findByText(/travel records this assessment read were confirmed/),
    ).toBeInTheDocument();
  });

  it("keeps the travel layer when no records were read", async () => {
    get.mockResolvedValue({ data: aDetail({ travel_inputs: [] }) });
    render(<RequirementDetail caseId="c1" requirementKey="residence.total_absences" />);
    await screen.findByRole("heading", { name: "Travel records used" });
    expect(screen.getByText("This assessment read no travel records.")).toBeInTheDocument();
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
});
