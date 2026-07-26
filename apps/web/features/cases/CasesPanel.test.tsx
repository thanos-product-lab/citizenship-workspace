import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const draftCase = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "My case",
  route_key: "SECTION_6_1_STANDARD",
  lifecycle_status: "DRAFT",
  support_status: "NOT_EVALUATED",
  current_phase: "SETTING_UP",
  created_at: "2026-07-26T00:00:00Z",
  updated_at: "2026-07-26T00:00:00Z",
  revision: 1,
};

const get = vi.fn();
const post = vi.fn();

// Stable reference, mirroring the real `useApiClient` (memoized via useMemo). A
// fresh object each render would refire the load effect.
const client = { GET: get, POST: post };

vi.mock("@/lib/api", () => ({
  useApiClient: () => client,
}));

import { CasesPanel } from "./CasesPanel";

describe("CasesPanel", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("shows the empty state when the user has no cases", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<CasesPanel />);
    await waitFor(() => {
      expect(screen.getByText(/no cases yet/i)).toBeInTheDocument();
    });
  });

  it("lists existing cases with their lifecycle status", async () => {
    get.mockResolvedValue({ data: [draftCase], error: undefined });
    render(<CasesPanel />);
    await waitFor(() => {
      expect(screen.getByText("My case")).toBeInTheDocument();
    });
    expect(screen.getByText("Setting up")).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    get.mockResolvedValueOnce({ data: undefined, error: { detail: "boom" } });
    render(<CasesPanel />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });

    get.mockResolvedValueOnce({ data: [], error: undefined });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => {
      expect(screen.getByText(/no cases yet/i)).toBeInTheDocument();
    });
  });

  it("creates a case and prepends it to the list", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    post.mockResolvedValue({ data: draftCase, error: undefined });
    render(<CasesPanel />);
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/case name/i), { target: { value: "My case" } });
    fireEvent.click(screen.getByRole("button", { name: /create case/i }));

    await waitFor(() => expect(screen.getByText("My case")).toBeInTheDocument());
    expect(post).toHaveBeenCalledWith("/api/v1/cases", { body: { title: "My case" } });
  });

  it("blocks submission of a blank title without calling the API", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<CasesPanel />);
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /create case/i }));
    await waitFor(() =>
      expect(screen.getByText(/give your case a name/i)).toBeInTheDocument(),
    );
    expect(post).not.toHaveBeenCalled();
  });
});
