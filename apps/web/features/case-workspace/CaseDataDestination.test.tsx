import "@testing-library/jest-dom/vitest";

import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderWithQuery as render } from "@/test/render";

const del = vi.fn();
const client = { GET: vi.fn(), DELETE: del, PUT: vi.fn(), POST: vi.fn() };

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

// The editing cards do their own fetching; stub them so this suite tests the
// destination's own composition and the destructive control.
vi.mock("@/features/timeline/ApplicationDateCard", () => ({
  ApplicationDateCard: () => <div>application date stub</div>,
}));
vi.mock("@/features/timeline/TravelHistory", () => ({
  TravelHistory: () => <div>travel history stub</div>,
}));

import { CaseDataDestination } from "./CaseDataDestination";

describe("CaseDataDestination", () => {
  beforeEach(() => del.mockReset());

  it("owns the editable case facts", () => {
    render(<CaseDataDestination caseId="c1" />);
    expect(screen.getByText("application date stub")).toBeInTheDocument();
    expect(screen.getByText("travel history stub")).toBeInTheDocument();
  });

  it("names itself Case data, not Residence", () => {
    // "Residence" was correct while this was the residence *section* of one scrolling
    // page. As the destination it described the whole page as being about residence,
    // with the delete control outside it as a sibling.
    render(<CaseDataDestination caseId="c1" />);
    expect(screen.getByRole("heading", { name: "Case data", level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Residence" })).not.toBeInTheDocument();
  });

  it("says that editing here makes conclusions stale, before the controls", () => {
    // The consequence stated up front is what makes the header's stale notice read as a
    // result of the user's own edit rather than as a surprise.
    render(<CaseDataDestination caseId="c1" />);
    expect(screen.getByText(/marks the conclusions drawn from it stale/i)).toBeInTheDocument();
  });

  it("separates deletion from the work above it and explains what it does", () => {
    render(<CaseDataDestination caseId="c1" />);
    expect(screen.getByRole("heading", { name: "Delete this case" })).toBeInTheDocument();
    expect(screen.getByText(/can’t be undone/i)).toBeInTheDocument();
  });

  it("requires a confirmation step before deleting", () => {
    render(<CaseDataDestination caseId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: /delete case/i }));
    // The destructive verb only appears after the first step, so a single stray click
    // cannot delete the case.
    expect(screen.getByRole("button", { name: /delete permanently/i })).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
  });

  it("moves focus to the confirm button rather than leaving it on an unmounted trigger", () => {
    render(<CaseDataDestination caseId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: /delete case/i }));
    expect(screen.getByRole("button", { name: /delete permanently/i })).toHaveFocus();
  });

  it("deletes on confirmation", async () => {
    del.mockResolvedValue({ data: { id: "c1" }, error: undefined });
    render(<CaseDataDestination caseId="c1" />);

    fireEvent.click(screen.getByRole("button", { name: /delete case/i }));
    fireEvent.click(screen.getByRole("button", { name: /delete permanently/i }));

    await waitFor(() =>
      expect(del).toHaveBeenCalledWith("/api/v1/cases/{case_id}", {
        params: { path: { case_id: "c1" } },
      }),
    );
  });

  it("returns focus to the trigger when the confirmation is cancelled", async () => {
    render(<CaseDataDestination caseId="c1" />);

    fireEvent.click(screen.getByRole("button", { name: /delete case/i }));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /delete case/i })).toHaveFocus(),
    );
    expect(del).not.toHaveBeenCalled();
  });

  it("reports a failed deletion instead of appearing to succeed", async () => {
    del.mockResolvedValue({ data: undefined, error: {} });
    render(<CaseDataDestination caseId="c1" />);

    fireEvent.click(screen.getByRole("button", { name: /delete case/i }));
    fireEvent.click(screen.getByRole("button", { name: /delete permanently/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not delete/i);
  });
});
