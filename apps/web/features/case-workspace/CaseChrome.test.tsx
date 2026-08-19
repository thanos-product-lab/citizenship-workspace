import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery as render } from "@/test/render";

const get = vi.fn();
const del = vi.fn();
const client = { GET: get, DELETE: del, PUT: vi.fn(), POST: vi.fn() };

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));
vi.mock("next/navigation", () => ({ usePathname: () => "/cases/c1" }));

// RouteOnboarding does its own fetching; stub it so this suite tests only the shell.
vi.mock("@/features/onboarding/RouteOnboarding", () => ({
  RouteOnboarding: () => <div>onboarding stub</div>,
}));

import { CaseChrome } from "./CaseChrome";

function aCase(overrides: Record<string, unknown>) {
  return {
    id: "c1",
    title: "My case",
    route_key: "SECTION_6_1_STANDARD",
    lifecycle_status: "DRAFT",
    support_status: "NOT_EVALUATED",
    current_phase: "SETTING_UP",
    created_at: "2026-07-27T00:00:00Z",
    updated_at: "2026-07-27T00:00:00Z",
    revision: 1,
    ...overrides,
  };
}

/** The chrome fetches the case; the header then fetches the overview. */
function mockCase(overrides: Record<string, unknown>) {
  get.mockImplementation((path: string) => {
    if (path === "/api/v1/cases/{case_id}") {
      return Promise.resolve({ data: aCase(overrides), error: undefined });
    }
    return Promise.resolve({ data: undefined, error: {}, response: { status: 500 } });
  });
}

describe("CaseChrome", () => {
  beforeEach(() => {
    get.mockReset();
    del.mockReset();
  });

  it("shows a not-found state for an unowned or missing case", async () => {
    get.mockResolvedValue({ data: undefined, error: {}, response: { status: 404 } });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    expect(await screen.findByRole("heading", { name: /case not found/i })).toBeInTheDocument();
    expect(screen.queryByText("destination")).not.toBeInTheDocument();
  });

  it("renders onboarding and no navigation for a draft case", async () => {
    mockCase({ lifecycle_status: "DRAFT" });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    expect(await screen.findByText("onboarding stub")).toBeInTheDocument();
    // Three destinations before the route is confirmed would offer two empty rooms and
    // compete with the single question onboarding is asking.
    expect(screen.queryByRole("navigation", { name: "Case navigation" })).not.toBeInTheDocument();
    expect(screen.queryByText("destination")).not.toBeInTheDocument();
  });

  it("keeps deletion available on a draft case, which has no Case data destination", async () => {
    mockCase({ lifecycle_status: "DRAFT" });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    expect(await screen.findByRole("button", { name: /delete case/i })).toBeInTheDocument();
  });

  it("renders the header, navigation and the destination for an active case", async () => {
    mockCase({ lifecycle_status: "ACTIVE", current_phase: "BUILDING_CASE" });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    expect(await screen.findByRole("heading", { name: "My case" })).toBeInTheDocument();
    expect(screen.getByText("Building your case")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Case navigation" })).toBeInTheDocument();
    expect(screen.getByText("destination")).toBeInTheDocument();
  });

  it("does not put deletion in the primary journey of an active case", async () => {
    // It lives at the foot of Case data, not beneath the readiness work.
    mockCase({ lifecycle_status: "ACTIVE" });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    await screen.findByRole("heading", { name: "My case" });
    expect(screen.queryByRole("button", { name: /delete case/i })).not.toBeInTheDocument();
  });

  it("shows the pending notice and no destination for a deletion-pending case", async () => {
    mockCase({ lifecycle_status: "DELETION_PENDING" });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );
    expect(await screen.findByText(/scheduled for deletion/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete case/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Case navigation" })).not.toBeInTheDocument();
    expect(screen.queryByText("destination")).not.toBeInTheDocument();
  });

  it("moves a deleted draft case to the pending notice and keeps focus", async () => {
    mockCase({ lifecycle_status: "DRAFT" });
    del.mockResolvedValue({
      data: aCase({ lifecycle_status: "DELETION_PENDING" }),
      error: undefined,
    });
    render(
      <CaseChrome caseId="c1">
        <div>destination</div>
      </CaseChrome>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /delete case/i }));
    fireEvent.click(await screen.findByRole("button", { name: /delete permanently/i }));

    await waitFor(() => expect(screen.getByText(/scheduled for deletion/i)).toBeInTheDocument());
    // Focus lands on the pending heading, not lost to <body> with the unmounted button.
    expect(screen.getByRole("heading", { name: "My case" })).toHaveFocus();
  });
});
