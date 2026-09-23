import { afterEach, describe, expect, it } from "vitest";

import { THEME_BOOT_SCRIPT, THEME_STORAGE_KEY, chooseTheme, nextTheme, readTheme } from "./theme";

afterEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

describe("the appearance choice", () => {
  it("steps System, Light, Dark, then back to System", () => {
    expect(nextTheme("system")).toBe("light");
    expect(nextTheme("light")).toBe("dark");
    expect(nextTheme("dark")).toBe("system");
  });

  it("pins a theme with the attribute the tokens read, and remembers it", () => {
    chooseTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(readTheme()).toBe("dark");
  });

  it("returns to the system theme by clearing both, not by storing 'system'", () => {
    chooseTheme("light");
    chooseTheme("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(readTheme()).toBe("system");
  });

  it("treats anything unrecognised in storage as System", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(readTheme()).toBe("system");
  });

  it("applies a saved choice from the boot script, before React is involved", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    new Function(THEME_BOOT_SCRIPT)();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("leaves the system theme alone when nothing is saved", () => {
    new Function(THEME_BOOT_SCRIPT)();
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
});
