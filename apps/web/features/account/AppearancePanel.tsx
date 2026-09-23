"use client";

import { useEffect, useState, type JSX } from "react";

import { THEME_LABELS, chooseTheme, readTheme, type ThemeChoice } from "@/lib/theme";

const CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

const DESCRIPTIONS: Record<ThemeChoice, string> = {
  system: "Follows your device, and changes when it does.",
  light: "Always light.",
  dark: "Always dark.",
};

/**
 * The Appearance page in the account window: three choices, all visible, one marked.
 *
 * A radio group, not buttons: exactly one is always chosen, arrow keys move between them,
 * and a screen reader announces "1 of 3, selected". Choosing applies at once, and because
 * this page is drawn in the product's tokens, the window re-colours around the choice as
 * well as the page behind it; the change is its own confirmation.
 *
 * **System names what it resolves to**, "System (currently light)", and keeps that current
 * if the device switches while the page is open. Without it, choosing System on a light
 * device looks identical to Light, which is the confusion this page replaced.
 */
export function AppearancePanel(): JSX.Element {
  // "system" until mounted: storage and the media query are browser-only, and reading them
  // during the server render would disagree with the client's first render.
  const [choice, setChoice] = useState<ThemeChoice>("system");
  const [systemDark, setSystemDark] = useState(false);

  useEffect(() => {
    setChoice(readTheme());
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    setSystemDark(query.matches);
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return (
    <div className="cw-appearance">
      <h2 className="cw-appearance__title" id="appearance-title">
        Appearance
      </h2>
      <p className="cw-appearance__lead" id="appearance-lead">
        How Citizenship Workspace looks on this device. Saved in this browser only.
      </p>
      <div
        className="cw-appearance__options"
        role="radiogroup"
        aria-labelledby="appearance-title"
        aria-describedby="appearance-lead"
      >
        {CHOICES.map((option) => (
          <label key={option} className="cw-appearance__option" data-selected={option === choice}>
            <input
              type="radio"
              name="appearance"
              value={option}
              checked={option === choice}
              onChange={() => {
                chooseTheme(option);
                setChoice(option);
              }}
            />
            <span className="cw-appearance__swatch" data-swatch={swatchFor(option, systemDark)} />
            <span className="cw-appearance__name">
              {THEME_LABELS[option]}
              {option === "system" ? (
                <span className="cw-appearance__resolved">
                  {" "}
                  (currently {systemDark ? "dark" : "light"})
                </span>
              ) : null}
            </span>
            <span className="cw-appearance__description">{DESCRIPTIONS[option]}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

/** Which preview a choice shows: System previews what the device is set to now. */
function swatchFor(option: ThemeChoice, systemDark: boolean): "light" | "dark" {
  if (option === "system") return systemDark ? "dark" : "light";
  return option;
}
