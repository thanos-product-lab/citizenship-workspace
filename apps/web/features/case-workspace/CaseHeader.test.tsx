import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery as render } from "@/test/render";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, DELETE: vi.fn(), PUT: vi.fn(), POST: post };

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

const pathname = { current: "/cases/c1" };
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

import { CaseHeader } from "./CaseHeader";

function aCase(overrides: Record<string, unknown> = {}) {
  return {
    id: "c1",
    title: "My case",
    route_key: "SECTION_6_1_STANDARD",
    lifecycle_status: "ACTIVE",
    support_status: "NOT_EVALUATED",
    current_phase: "RESOLVING_ISSUES",
    created_at: "2026-07-27T00:00:00Z",
    updated_at: "2026-07-27T00:00:00Z",
    revision: 1,
    ...overrides,
  };
}

function anOverview(overrides: Record<string, unknown> = {}) {
  return {
    case_id: "c1",
    title: "My case",
    route_key: "SECTION_6_1_STANDARD",
    lifecycle_status: "ACTIVE",
    current_phase: "RESOLVING_ISSUES",
    application_date: "2027-04-15",
    last_assessed_at: "2026-08-18T11:00:00Z",
    groups: [],
    conclusion_counts: [{ conclusion: "SUPPORTED", count: 7 }],
    priority_actions: [],
    priority_actions_hidden: 0,
    needs_attention: 0,
    not_yet_assessed: 6,
    stale: 0,
    open_issue_count: 0,
    open_issues: 0,
    total_requirements: 15,
    ...overrides,
  };
}

function mock(overview: Record<string, unknown> = {}) {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/cases/{case_id}/overview") {
      return Promise.resolve({ data: anOverview(overview), error: undefined });
    }
    return Promise.resolve({ data: undefined, error: {}, response: { status: 404 } });
  });
}

function renderHeader(caseOverrides: Record<string, unknown> = {}) {
  return render(<CaseHeader caseData={aCase(caseOverrides)} headingRef={createRef()} />);
}

describe("CaseHeader", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    pathname.current = "/cases/c1";
  });

  it("names the case and its derived phase once", async () => {
    mock();
    renderHeader();
    expect(screen.getByRole("heading", { name: "My case" })).toBeInTheDocument();
    expect(screen.getByText("Resolving issues")).toBeInTheDocument();
    // The phase is labelled for screen readers rather than being an unexplained chip.
    expect(screen.getByText("Case phase:")).toBeInTheDocument();
    await waitFor(() => expect(get).toHaveBeenCalled());
  });

  it("pairs each case fact with its value in a description list", async () => {
    // dt/dd outside a dl lose the pairing entirely; the proposed application date would
    // read as two unrelated fragments.
    mock();
    const { container } = renderHeader();
    await screen.findByText("15 April 2027");
    const dl = container.querySelector("dl.cw-case-header__facts");
    expect(dl?.querySelectorAll("dt")).toHaveLength(3);
    expect(dl?.querySelectorAll("dd")).toHaveLength(3);
  });

  it("omits a fact it does not have rather than showing a blank", async () => {
    mock({ application_date: null, last_assessed_at: null });
    renderHeader();
    await screen.findByText("Standard five-year route");
    expect(screen.queryByText("Proposed application date")).not.toBeInTheDocument();
    expect(screen.queryByText("Last assessed")).not.toBeInTheDocument();
  });

  it("shows no readiness summary — that belongs to Overview", async () => {
    mock({ needs_attention: 3 });
    renderHeader();
    await screen.findByText("Standard five-year route");
    expect(screen.queryByText(/needs your attention/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Requirements by state" })).not.toBeInTheDocument();
  });

  it("shows no fraction, ratio or percentage", async () => {
    mock({ needs_attention: 1, not_yet_assessed: 6 });
    const { container } = renderHeader();
    await screen.findByText("Standard five-year route");
    expect(container.textContent).not.toMatch(/%|\d+\s*\/\s*\d+|\d+ of \d+/);
  });

  describe("currency follows the user across destinations", () => {
    it("states unrechecked conclusions without claiming they still hold", async () => {
      mock({ stale: 5 });
      renderHeader();
      expect(await screen.findByText(/5 conclusions have not been rechecked/)).toBeInTheDocument();
      expect(screen.getByText(/shown as they were reached, marked stale/)).toBeInTheDocument();
      // The one thing a stale result cannot tell us is that its conclusion still stands.
      expect(screen.queryByText(/still (stands|holds|applies)/i)).not.toBeInTheDocument();
    });

    it("is present on Case data, where the edit that causes staleness happens", async () => {
      // The point of putting currency in the header: a user edits a trip here, and the
      // consequence is stated on the page where they made the change.
      pathname.current = "/cases/c1/data";
      mock({ stale: 5 });
      renderHeader();
      expect(await screen.findByText(/5 conclusions have not been rechecked/)).toBeInTheDocument();
    });

    it("says nothing about staleness when nothing is stale", async () => {
      mock({ stale: 0 });
      renderHeader();
      await screen.findByText("Standard five-year route");
      expect(screen.queryByText(/have not been rechecked/)).not.toBeInTheDocument();
    });

    it("uses the singular for one stale conclusion", async () => {
      mock({ stale: 1 });
      renderHeader();
      expect(await screen.findByText(/1 conclusion has not been rechecked/)).toBeInTheDocument();
    });
  });

  describe("recalculate", () => {
    it("offers recalculation once the case has been assessed", async () => {
      mock();
      renderHeader();
      expect(await screen.findByRole("button", { name: "Recalculate" })).toBeInTheDocument();
    });

    it("does not offer recalculation before the first assessment", async () => {
      // The first run is offered by the requirements list's empty state, where its absence
      // is being explained.
      mock({ conclusion_counts: [] });
      renderHeader();
      await screen.findByText("Standard five-year route");
      expect(screen.queryByRole("button", { name: "Recalculate" })).not.toBeInTheDocument();
    });

    it("invalidates every case-scoped query when a recalculation lands", async () => {
      // This replaces four hand-wired refresh counters. The bug they kept producing was a
      // reader nobody remembered to wire: the phase chip, the detail page and the overview
      // each went stale in turn during M4. Invalidating the case subtree reaches readers
      // that did not exist when this code was written — which now includes readers on
      // other destinations entirely.
      mock();
      const { client: queryClient } = renderHeader();
      const button = await screen.findByRole("button", { name: "Recalculate" });

      const invalidate = vi.spyOn(queryClient, "invalidateQueries");
      post.mockResolvedValue({
        data: {
          assessment_run_id: "r1",
          mode: "TRUSTED",
          trigger_type: "USER_REQUESTED",
          result_count: 1,
          requirements: [{ conclusion: "SUPPORTED" }],
        },
      });
      fireEvent.click(button);

      await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["cases", "c1"] }));
    });

    it("refetches when a recalculation fails, because the server recorded the failure", async () => {
      // This used to assert the opposite, on the reasoning that a failed run changed
      // nothing so there was nothing to refetch. That stopped being true when a failed
      // recalculation started leaving a durable record — a FAILED run and a
      // PROCESSING_FAILURE item in the issue queue. Without the refetch the alert tells
      // the user to reload the page to find something the app could already show them.
      //
      // It also covers the case this hook always had to allow for: a timeout or a dropped
      // response *after* the run committed, where the server state moved and the client
      // never heard about it.
      mock();
      const { client: queryClient } = renderHeader();
      const button = await screen.findByRole("button", { name: "Recalculate" });

      const invalidate = vi.spyOn(queryClient, "invalidateQueries");
      post.mockResolvedValue({ error: { detail: "boom" } });
      fireEvent.click(button);

      await screen.findByRole("alert");
      await waitFor(() =>
        expect(invalidate).toHaveBeenCalledWith({ queryKey: ["cases", "c1"] }),
      );
    });

    it("reports a failed recalculation visibly, not only to a live region", async () => {
      // The button that failed lives here, so the report has to as well. An announcement
      // alone would leave a sighted user watching the button settle and nothing change.
      mock();
      renderHeader();
      const button = await screen.findByRole("button", { name: "Recalculate" });

      post.mockResolvedValue({ error: { detail: "boom" } });
      fireEvent.click(button);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("couldn’t confirm whether that recalculation ran");
      // Not "nothing has changed": a dropped response after the run committed would make
      // that false while the figures on screen were already out of date.
      expect(alert).not.toHaveTextContent(/nothing has changed/i);
    });
  });

  describe("navigation", () => {
    it("offers the destinations as links, not tabs", async () => {
      mock();
      renderHeader();
      const nav = await screen.findByRole("navigation", { name: "Case navigation" });
      expect(nav).toBeInTheDocument();
      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Requirements" })).toHaveAttribute(
        "href",
        "/cases/c1/requirements",
      );
    });

    it("carries the open issue count inside the Issues link, not as an orphan badge", async () => {
      mock({ open_issue_count: 4 });
      renderHeader();
      // One accessible name, "Issues 4 open issues" — a number rendered beside the link
      // would be announced with nothing tying it to what it counts.
      const link = await screen.findByRole("link", { name: /Issues\s*4\s*open issues/i });
      expect(link).toHaveAttribute("href", "/cases/c1/issues");
    });

    it("shows no count when nothing is open", async () => {
      // A "0" reads as a state worth looking at. Absence is the honest rendering of
      // nothing to do.
      mock({ open_issue_count: 0 });
      renderHeader();
      const link = await screen.findByRole("link", { name: "Issues" });
      expect(link.textContent).toBe("Issues");
    });

    it("marks the current destination with aria-current", async () => {
      pathname.current = "/cases/c1/requirements";
      mock();
      renderHeader();
      const current = await screen.findByRole("link", { name: "Requirements" });
      expect(current).toHaveAttribute("aria-current", "page");
      expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
    });

    it("marks Requirements current while a requirement detail is open", async () => {
      pathname.current = "/cases/c1/requirements/residence.total_absences";
      mock();
      renderHeader();
      expect(await screen.findByRole("link", { name: "Requirements" })).toHaveAttribute(
        "aria-current",
        "page",
      );
    });
  });
});
