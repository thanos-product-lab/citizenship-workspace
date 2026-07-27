import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const savedDraft = {
  case_id: "c1",
  version_number: 1,
  review_state: "DRAFT",
  date_of_birth: "1990-05-01",
  status_type: "ILR",
  status_granted_on: null,
  married_to_british_citizen: null,
  may_already_be_british: null,
  created_at: "2026-07-26T00:00:00Z",
  revision: 2,
};

const get = vi.fn();
const put = vi.fn();
const post = vi.fn();
const client = { GET: get, PUT: put, POST: post }; // stable ref, mirrors useMemo'd hook

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { RouteOnboarding } from "./RouteOnboarding";

function decision(overrides: Record<string, unknown>) {
  return {
    data: {
      support_status: "SUPPORTED",
      lifecycle_status: "ACTIVE",
      conclusion: "SUPPORTED",
      summary_code: "ROUTE_STANDARD_CONFIRMED",
      confirmed_version_number: 2,
      rule_set: "2026.07.0",
      semantic_version: "1.0.0",
      requirements: [],
      ...overrides,
    },
    error: undefined,
    response: { status: 200 },
  };
}

describe("RouteOnboarding", () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
    post.mockReset();
  });

  it("starts blank when no draft has been saved", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    render(<RouteOnboarding caseId="c1" />);
    // The heading is present in every state; wait for a ready-state control.
    expect(await screen.findByLabelText(/date of birth/i)).toHaveValue("");
  });

  it("resumes previously saved answers", async () => {
    get.mockResolvedValue({ data: savedDraft, error: undefined });
    render(<RouteOnboarding caseId="c1" />);
    expect(await screen.findByLabelText(/date of birth/i)).toHaveValue("1990-05-01");
    expect(screen.getByLabelText(/current immigration status/i)).toHaveValue("ILR");
  });

  it("saves the whole answer set and echoes the new revision", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    put.mockResolvedValue({ data: savedDraft, error: undefined, response: { status: 200 } });
    render(<RouteOnboarding caseId="c1" />);

    fireEvent.change(await screen.findByLabelText(/current immigration status/i), {
      target: { value: "ILR" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save answers/i }));

    await waitFor(() => expect(screen.getByText(/^saved\.$/i)).toBeInTheDocument());
    expect(put).toHaveBeenCalledWith("/api/v1/cases/{case_id}/route-profile", {
      params: { path: { case_id: "c1" } },
      body: expect.objectContaining({ status_type: "ILR", expected_revision: null }),
    });
  });

  it("surfaces a conflict when the draft changed elsewhere", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    put.mockResolvedValue({ data: undefined, error: { detail: "x" }, response: { status: 409 } });
    render(<RouteOnboarding caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /save answers/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/changed elsewhere/i),
    );
  });

  it("confirms a supported route, shows the set-up outcome, and hides the form", async () => {
    get.mockResolvedValue({ data: savedDraft, error: undefined });
    put.mockResolvedValue({ data: { ...savedDraft, revision: 3 }, error: undefined });
    post.mockResolvedValue(decision({}));
    render(<RouteOnboarding caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /confirm route/i }));

    expect(await screen.findByRole("heading", { name: /your case is set up/i })).toBeInTheDocument();
    // The form is gone once the route is supported (the case is now active).
    expect(screen.queryByLabelText(/date of birth/i)).not.toBeInTheDocument();
    // Confirm saved the on-screen answers first, then asked for the decision.
    expect(put).toHaveBeenCalled();
    expect(post).toHaveBeenCalledWith("/api/v1/cases/{case_id}/route-profile/confirm", {
      params: { path: { case_id: "c1" } },
      body: { expected_revision: 3 },
    });
  });

  it("shows a stop outcome for the spouse route and keeps the form for editing", async () => {
    get.mockResolvedValue({ data: savedDraft, error: undefined });
    put.mockResolvedValue({ data: { ...savedDraft, revision: 3 }, error: undefined });
    post.mockResolvedValue(
      decision({
        support_status: "UNSUPPORTED",
        lifecycle_status: "DRAFT",
        conclusion: "PROFESSIONAL_REVIEW_RECOMMENDED",
        summary_code: "ROUTE_SPOUSE_UNSUPPORTED",
      }),
    );
    render(<RouteOnboarding caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /confirm route/i }));

    expect(await screen.findByRole("heading", { name: /spouse route/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/date of birth/i)).toBeInTheDocument(); // still editable
  });

  it("reports missing answers when confirming an incomplete profile", async () => {
    get.mockResolvedValue({ data: savedDraft, error: undefined });
    put.mockResolvedValue({ data: { ...savedDraft, revision: 3 }, error: undefined });
    post.mockResolvedValue({
      data: undefined,
      error: { missing_fields: ["married_to_british_citizen"] },
      response: { status: 422 },
    });
    render(<RouteOnboarding caseId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: /confirm route/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/spouse-route question/i),
    );
    // The named field is flagged invalid, not just mentioned in a banner.
    await waitFor(() =>
      expect(screen.getByLabelText(/spouse or civil partner/i)).toHaveAttribute(
        "aria-invalid",
        "true",
      ),
    );
  });
});
