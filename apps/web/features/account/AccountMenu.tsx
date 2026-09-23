"use client";

import { UserButton } from "@clerk/nextjs";
import { useEffect, useState, type JSX } from "react";

import { THEME_LABELS, chooseTheme, nextTheme, readTheme, type ThemeChoice } from "@/lib/theme";

/**
 * The account menu: Clerk's own items, plus the appearance choice.
 *
 * One item that steps through System, Light and Dark rather than three: the menu stays the
 * short list Clerk draws, and the label always says what is active now. Clerk closes the
 * menu on click; the page has already changed theme, so nothing more needs saying.
 *
 * Shared by the case list and the case header, so the choice is reachable wherever the
 * avatar is.
 */
export function AccountMenu(): JSX.Element {
  // "system" until mounted: the server cannot read this browser's storage, and rendering
  // the stored value on the server would disagree with the client on first render.
  const [theme, setTheme] = useState<ThemeChoice>("system");
  useEffect(() => setTheme(readTheme()), []);

  return (
    <UserButton>
      <UserButton.MenuItems>
        <UserButton.Action label="manageAccount" />
        <UserButton.Action
          label={`Appearance: ${THEME_LABELS[theme]}`}
          labelIcon={<AppearanceIcon />}
          onClick={() => {
            const next = nextTheme(theme);
            chooseTheme(next);
            setTheme(next);
          }}
        />
        <UserButton.Action label="signOut" />
      </UserButton.MenuItems>
    </UserButton>
  );
}

/** A half-filled circle: the usual mark for light and dark together. */
function AppearanceIcon(): JSX.Element {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
      <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor" />
    </svg>
  );
}
