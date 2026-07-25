import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// Mock the API hook (which wraps Clerk's useAuth), so the component under test
// needs neither a live backend nor a Clerk session.
vi.mock("@/lib/api", () => ({
  useApiClient: () => ({
    GET: vi.fn().mockResolvedValue({
      data: { user_id: "user_123", session_id: "sess_1", email: "ada@example.com" },
      error: undefined,
    }),
  }),
}));

import { CurrentUserPanel } from "./CurrentUserPanel";

describe("CurrentUserPanel", () => {
  it("renders the signed-in user from /api/v1/me", async () => {
    render(<CurrentUserPanel />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("ada@example.com")).toBeInTheDocument();
    });
  });
});
