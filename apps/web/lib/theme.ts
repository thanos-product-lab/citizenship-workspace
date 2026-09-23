/**
 * The user's appearance choice: follow the system, or pin light or dark.
 *
 * The themes themselves live entirely in `tokens.css`: dark via `prefers-color-scheme`, and
 * a `data-theme` attribute on `<html>` that overrides it either way. This module only
 * decides whether that attribute is set, and remembers the choice in this browser.
 *
 * `localStorage`, not an account setting: it is a per-device convenience, like a zoom
 * level, and nothing about a case depends on it. Every access is guarded, because storage
 * can throw (private windows, blocked site data), and the only consequence of a failure
 * should be following the system.
 */

export type ThemeChoice = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "cw-theme";

export const THEME_LABELS: Record<ThemeChoice, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
};

export function readTheme(): ThemeChoice {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    return "system";
  }
}

/** Set or clear the attribute the tokens key off, and remember the choice. */
export function chooseTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  try {
    if (choice === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Applied for this page view; it just will not be remembered.
  }
}

/**
 * Runs in `<head>` before the page paints, so a saved Light or Dark choice is in place for
 * the first frame. Without it the page would render in the system theme and switch once
 * React loaded, a visible flash on every load, and on a slow connection a long one.
 * Deliberately tiny and dependency-free, since it blocks rendering.
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_STORAGE_KEY}");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}})();`;
