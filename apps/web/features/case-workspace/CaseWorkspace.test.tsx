import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const del = vi.fn();
const client = { GET: get, DELETE: del, PUT: vi.fn(), POST: vi.fn() };

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

// RouteOnboarding and ResidencePanel do their own fetching; stub them so this suite
// tests only the shell.
vi.mock("@/features/onboarding/RouteOnboarding", () => ({
  RouteOnboarding: () => <div>onboarding stub</div>,
}));
vi.mock("@/features/timeline/ResidencePanel", () => ({
  ResidencePanel: () => <div>residence stub</div>,
}));

import { CaseWorkspace } from "./CaseWorkspace";

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

describe("CaseWorkspace", () => {
  beforeEach(() => {
    get.mockReset();
    del.mockReset();
  });

  it("shows a not-found state for an unowned or missing case", async () => {
    get.mockResolvedValue({ data: undefined, error: {}, response: { status: 404 } });
    render(<CaseWorkspace caseId="c1" />);
    expect(await screen.findByRole("heading", { name: /case not found/i })).toBeInTheDocument();
  });

  it("renders onboarding for a draft case", async () => {
    get.mockResolvedValue({ data: aCase({ lifecycle_status: "DRAFT" }), error: undefined });
    render(<CaseWorkspace caseId="c1" />);
    expect(await screen.findByText("onboarding stub")).toBeInTheDocument();
  });

  it("renders the workspace shell with the phase pill and residence for an active case", async () => {
    get.mockResolvedValue({
      data: aCase({ lifecycle_status: "ACTIVE", current_phase: "BUILDING_CASE" }),
      error: undefined,
    });
    render(<CaseWorkspace caseId="c1" />);
    expect(await screen.findByRole("heading", { name: "My case" })).toBeInTheDocument();
    // The phase shows as a pill next to the title; residence is the case's content.
    expect(screen.getByText("Building your case")).toBeInTheDocument();
    expect(screen.getByText("residence stub")).toBeInTheDocument();
    // No roadmap scaffold: unbuilt sections aren't advertised.
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
  });

  it("shows the pending notice and no delete control for a deletion-pending case", async () => {
    get.mockResolvedValue({
      data: aCase({ lifecycle_status: "DELETION_PENDING" }),
      error: undefined,
    });
    render(<CaseWorkspace caseId="c1" />);
    expect(await screen.findByText(/scheduled for deletion/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete case/i })).not.toBeInTheDocument();
  });

  it("confirms then deletes, moving the case to the pending notice", async () => {
    get.mockResolvedValue({ data: aCase({ lifecycle_status: "ACTIVE" }), error: undefined });
    del.mockResolvedValue({ data: aCase({ lifecycle_status: "DELETION_PENDING" }), error: undefined });
    render(<CaseWorkspace caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /delete case/i }));
    // A confirm step guards the destructive action.
    fireEvent.click(await screen.findByRole("button", { name: /delete permanently/i }));

    await waitFor(() => expect(screen.getByText(/scheduled for deletion/i)).toBeInTheDocument());
    expect(del).toHaveBeenCalledWith("/api/v1/cases/{case_id}", {
      params: { path: { case_id: "c1" } },
    });
    // Focus lands on the pending heading, not lost to <body>.
    expect(screen.getByRole("heading", { name: "My case" })).toHaveFocus();
  });

  it("can cancel the delete confirmation", async () => {
    get.mockResolvedValue({ data: aCase({ lifecycle_status: "ACTIVE" }), error: undefined });
    render(<CaseWorkspace caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /delete case/i }));
    fireEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    // Cancelling returns focus to the trigger rather than dropping it to <body>.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /delete case/i })).toHaveFocus(),
    );
    expect(del).not.toHaveBeenCalled();
  });
});
