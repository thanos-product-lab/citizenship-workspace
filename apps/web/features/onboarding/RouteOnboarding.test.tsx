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
const client = { GET: get, PUT: put }; // stable reference, mirrors useMemo'd hook

vi.mock("@/lib/api", () => ({ useApiClient: () => client }));

import { RouteOnboarding } from "./RouteOnboarding";

describe("RouteOnboarding", () => {
  beforeEach(() => {
    get.mockReset();
    put.mockReset();
  });

  it("starts blank when no draft has been saved", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    render(<RouteOnboarding caseId="c1" />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /your route/i })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/date of birth/i)).toHaveValue("");
  });

  it("resumes previously saved answers", async () => {
    get.mockResolvedValue({ data: savedDraft, error: undefined });
    render(<RouteOnboarding caseId="c1" />);
    await waitFor(() => expect(screen.getByLabelText(/date of birth/i)).toHaveValue("1990-05-01"));
    expect(screen.getByLabelText(/current immigration status/i)).toHaveValue("ILR");
  });

  it("saves the whole answer set and echoes the new revision", async () => {
    get.mockResolvedValue({ data: null, error: undefined });
    put.mockResolvedValue({ data: savedDraft, error: undefined, response: { status: 200 } });
    render(<RouteOnboarding caseId="c1" />);
    await waitFor(() => screen.getByRole("heading", { name: /your route/i }));

    fireEvent.change(screen.getByLabelText(/current immigration status/i), {
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
    await waitFor(() => screen.getByRole("heading", { name: /your route/i }));

    fireEvent.click(screen.getByRole("button", { name: /save answers/i }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/changed elsewhere/i),
    );
  });
});
