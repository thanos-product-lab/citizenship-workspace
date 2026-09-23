import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "@/lib/theme";

import { AccountMenu } from "./AccountMenu";

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("AccountMenu", () => {
  it("names the active appearance and moves to the next on click", () => {
    render(<AccountMenu />);

    fireEvent.click(screen.getByRole("button", { name: "Appearance: System" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(screen.getByRole("button", { name: "Appearance: Light" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Appearance: Light" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    fireEvent.click(screen.getByRole("button", { name: "Appearance: Dark" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("starts from the choice saved in this browser", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: "Appearance: Dark" })).toBeInTheDocument();
  });
});
