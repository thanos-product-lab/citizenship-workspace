"use client";

import { UserButton } from "@clerk/nextjs";
import type { JSX } from "react";

import { AppearancePanel } from "./AppearancePanel";

/**
 * The account menu: Clerk's own items, plus Appearance.
 *
 * Appearance opens a page in Clerk's account window rather than acting in the menu. The
 * first version was a menu item that stepped System, Light, Dark on each click, and it had
 * two faults that no amount of polish fixes: Clerk closes the menu on every click, and one
 * step in any such cycle changes nothing on screen, because System always looks like one
 * of the other two. Going System to Light on a light system read as a click that did
 * nothing. The page shows all three choices at once, with System naming what it resolves
 * to, and stays open while the theme changes around it.
 *
 * Shared by the case list and the case header, so it is reachable wherever the avatar is.
 */
export function AccountMenu(): JSX.Element {
  return (
    <UserButton>
      <UserButton.MenuItems>
        <UserButton.Action label="manageAccount" />
        <UserButton.Action label="Appearance" labelIcon={<AppearanceIcon />} open="appearance" />
        <UserButton.Action label="signOut" />
      </UserButton.MenuItems>
      <UserButton.UserProfilePage
        label="Appearance"
        url="appearance"
        labelIcon={<AppearanceIcon />}
      >
        <AppearancePanel />
      </UserButton.UserProfilePage>
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
