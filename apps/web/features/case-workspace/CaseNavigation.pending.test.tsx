import "@testing-library/jest-dom/vitest";

import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { renderWithQuery as render } from "@/test/render";

// Every link reports itself as on its way, as the clicked one does mid-navigation.
vi.mock("next/link", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/link")>()),
  useLinkStatus: () => ({ pending: true }),
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/cases/c1/timeline" }));
vi.mock("@/lib/api", () => ({
  useApiClient: () => ({ GET: vi.fn(() => new Promise(() => {})) }),
}));

import CaseDestinationLoading from "@/app/cases/[caseId]/loading";

import { CaseNavigation } from "./CaseNavigation";

describe("a tab switch in progress", () => {
  it("marks the clicked tab at once, without announcing it", () => {
    render(<CaseNavigation caseId="c1" />);

    const issues = screen.getByRole("link", { name: /^Issues/ });
    const mark = issues.querySelector(".cw-case-nav__pending");
    expect(mark).not.toBeNull();
    // The destination's loading state says it in words; the mark stays silent.
    expect(mark).toHaveAttribute("aria-hidden", "true");
    // Still the page on screen that is current, not the one on its way.
    expect(screen.getByRole("link", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
  });

  it("shows the destination's skeleton, with the words for a screen reader", () => {
    render(<CaseDestinationLoading />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(screen.getByTestId("destination-skeleton")).toHaveAttribute("aria-hidden", "true");
  });
});
