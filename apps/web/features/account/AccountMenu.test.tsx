import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme";

import { AccountMenu } from "./AccountMenu";
import { AppearancePanel } from "./AppearancePanel";

/** A device whose colour scheme the test sets. */
function deviceIs(dark: boolean) {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: dark,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia;
}

beforeEach(() => deviceIs(false));

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("AppearancePanel", () => {
  it("shows all three choices at once, with the current one selected", () => {
    render(<AppearancePanel />);

    const group = screen.getByRole("radiogroup", { name: "Appearance" });
    expect(group).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.getByRole("radio", { name: /System/ })).toBeChecked();
  });

  it("says what System resolves to, so choosing it never looks like nothing happened", () => {
    deviceIs(true);
    render(<AppearancePanel />);
    expect(screen.getByRole("radio", { name: /System \(currently dark\)/ })).toBeInTheDocument();
  });

  it("applies a choice at once and remembers it", () => {
    render(<AppearancePanel />);

    fireEvent.click(screen.getByRole("radio", { name: /^Dark/ }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("radio", { name: /^Dark/ })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: /System/ }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("starts from the choice saved in this browser", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    render(<AppearancePanel />);
    expect(screen.getByRole("radio", { name: /^Light/ })).toBeChecked();
  });
});

describe("AccountMenu", () => {
  it("adds the Appearance page to the account window", () => {
    render(<AccountMenu />);
    expect(screen.getByRole("region", { name: "Appearance page" })).toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Appearance" })).toBeInTheDocument();
  });
});
