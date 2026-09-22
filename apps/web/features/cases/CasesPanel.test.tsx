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

  it("says the case limit was reached instead of telling the user to try again", async () => {
    /**
     * Every failure used to collapse into "Could not create the case. Please try again."
     * For this one that advice is the single thing guaranteed not to work: the refusal is
     * a limit, so retrying repeats it exactly, and nothing said a limit existed or that
     * deleting a finished case is the way out.
     *
     * The server had written all of it. `TooManyCases` carries a stable code and puts
     * `held` and `limit` in the body under a comment saying it is there "so the client can
     * say 10 of 10" — the numbers come from the server precisely so this file does not
     * hold a copy of `max_cases_per_user` that could drift.
     */
    get.mockResolvedValue({ data: [], error: undefined });
    post.mockResolvedValue({
      data: undefined,
      error: { detail: "…", code: "TOO_MANY_CASES", held: 10, limit: 10 },
      response: { status: 409 },
    });
    render(<CasesPanel />);
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/case name/i), { target: { value: "One too many" } });
    fireEvent.click(screen.getByRole("button", { name: /create case/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/10 of 10/);
    expect(alert).toHaveTextContent(/delete a case you have finished with/i);
    expect(alert).not.toHaveTextContent(/try again/i);
  });

  it("still offers a retry for a failure it cannot name", async () => {
    // The fallback is right here and only here: an unknown failure may well be transient.
    get.mockResolvedValue({ data: [], error: undefined });
    post.mockResolvedValue({ data: undefined, error: {}, response: { status: 500 } });
    render(<CasesPanel />);
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/case name/i), { target: { value: "Boom" } });
    fireEvent.click(screen.getByRole("button", { name: /create case/i }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/could not create the case/i),
    );
  });

  it("blocks submission of a blank title without calling the API", async () => {
    get.mockResolvedValue({ data: [], error: undefined });
    render(<CasesPanel />);
    await waitFor(() => expect(screen.getByText(/no cases yet/i)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /create case/i }));
    await waitFor(() =>
      // role="alert" so a screen reader hears it even though focus isn't on the input.
      expect(screen.getByRole("alert")).toHaveTextContent(/give your case a name/i),
    );
    expect(post).not.toHaveBeenCalled();
  });
});
