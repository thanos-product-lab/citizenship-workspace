/**
 * Clerk themed with the product's tokens, applied once on `ClerkProvider` so every Clerk
 * surface shares it: the sign-in and sign-up cards, the account menu, and the "Manage
 * account" window. Before this lived on the sign-in pages alone, the account menu kept
 * Clerk's default look and its orange development strip.
 *
 * Every colour is a `--cw-*` custom property, so each surface follows the light and dark
 * themes with the rest of the product rather than staying Clerk's white in both.
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "var(--cw-accent)",
    // Clerk otherwise picks white, which fails contrast on the dark theme's light accent.
    // The token is dark text there, white in the light theme.
    colorTextOnPrimaryBackground: "var(--cw-accent-contrast)",
    colorText: "var(--cw-text)",
    colorTextSecondary: "var(--cw-text-muted)",
    colorBackground: "var(--cw-surface)",
    colorInputBackground: "var(--cw-surface)",
    colorInputText: "var(--cw-text)",
    colorDanger: "var(--cw-status-not-satisfied)",
    colorNeutral: "var(--cw-text)",
    fontFamily: "var(--cw-font-sans)",
    borderRadius: "var(--cw-radius-md)",
  },
  layout: {
    // Hides the orange "Development mode" strip that development keys add to every Clerk
    // card and menu, so local screenshots and demo captures show the product as designed.
    // It changes nothing about how authentication works; "unsafe" only means Clerk stops
    // reminding us these are development keys. A public deployment should move to a
    // production instance anyway (CLAUDE.md §13, Clerk setup), where the strip is absent.
    unsafe_disableDevelopmentModeWarnings: true,
  },
};
