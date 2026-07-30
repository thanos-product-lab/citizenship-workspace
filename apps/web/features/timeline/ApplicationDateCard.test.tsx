import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const get = vi.fn();
const post = vi.fn();
const client = { GET: get, POST: post, PUT: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() };
vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { ApplicationDateCard } from "./ApplicationDateCard";

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

describe("ApplicationDateCard", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });

  it("loads and shows the current date with an update action", async () => {
    get.mockResolvedValue({ data: aDate(), error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    const input = (await screen.findByLabelText("Application date")) as HTMLInputElement;
    expect(input.value).toBe("2027-04-15");
    expect(screen.getByRole("button", { name: /update date/i })).toBeInTheDocument();
  });

  it("offers a set action when no date is chosen yet", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    render(<ApplicationDateCard caseId="c1" />);
    expect(await screen.findByRole("button", { name: /set date/i })).toBeInTheDocument();
  });

  it("saves a new date and confirms it", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    post.mockResolvedValue({ data: aDate({ application_date: "2027-05-01", revision: 2 }) });
    render(<ApplicationDateCard caseId="c1" />);

    fireEvent.change(await screen.findByLabelText("Application date"), {
      target: { value: "2027-05-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: /set date/i }));

    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith("/api/v1/cases/{case_id}/application-dates/select", {
      params: { path: { case_id: "c1" } },
      body: { application_date: "2027-05-01", expected_revision: null },
    });
  });

  it("surfaces a concurrency conflict with a reload option", async () => {
    get.mockResolvedValue({ data: aDate(), error: undefined });
    post.mockResolvedValue({ data: undefined, response: { status: 409 } });
    render(<ApplicationDateCard caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /update date/i }));
    expect(await screen.findByText(/changed elsewhere/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload the latest/i })).toBeInTheDocument();
  });

  it("shows an error with retry when loading fails", async () => {
    get.mockResolvedValue({ data: undefined, error: {} });
    render(<ApplicationDateCard caseId="c1" />);
    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
    // Retry re-fetches.
    get.mockResolvedValue({ data: aDate(), error: undefined });
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /update date/i })).toBeInTheDocument());
  });
});
