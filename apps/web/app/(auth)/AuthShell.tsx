import { StatusGlyph } from "@cw/design-system";
import type { JSX, ReactNode } from "react";

/**
 * The way in, in the product's own voice: shared by sign-in and sign-up, so the two pages
 * say the same thing about the product and cannot drift apart.
 *
 * **Clerk still does all of the authentication.** The pages lay the product out around
 * Clerk's `<SignIn>` and `<SignUp>` and theme them; they do not rebuild the forms on
 * Clerk's lower-level hooks. Passwords, one-time codes, second factors, social providers,
 * verification, errors and recovery all stay Clerk's, which is the point of using it: a
 * hand-built form would take on each of those flows, and a custom authentication path is
 * on CLAUDE.md's rejected list.
 *
 * **One `h1`, and it is Clerk's.** The card's title is rendered by Clerk as an `h1` and
 * changes with each step ("Check your email", "Enter your password"), so it is the heading
 * that names what the user is doing. The introduction beside it is prose.
 */
export function AuthShell({ children }: { children: ReactNode }): JSX.Element {
  return (
    <main className="cw-auth">
      <div className="cw-auth__intro">
        <p className="cw-auth__brand">Citizenship Workspace</p>
        <p className="cw-auth__statement">
          Prepare your UK citizenship case, with the working shown.
        </p>
        <p className="cw-auth__lead">
          A private workspace for adults with settled status preparing a naturalisation
          application on the standard five-year route.
        </p>
        <ul className="cw-auth__points">
          <li>
            <StatusGlyph name="check" size={16} />
            <span>Nothing read from a document counts until you confirm it.</span>
          </li>
          <li>
            <StatusGlyph name="scale" size={16} />
            <span>Every conclusion shows the dates, rule and sources behind it.</span>
          </li>
          <li>
            <StatusGlyph name="clock" size={16} />
            <span>A conclusion that is out of date says so, and is never shown as current.</span>
          </li>
        </ul>
        <p className="cw-auth__note">
          This prototype helps you prepare. It does not give legal advice or predict a
          decision.
        </p>
      </div>

      <div className="cw-auth__panel">{children}</div>
    </main>
  );
}

export const SIGN_IN_PATH = "/sign-in";
export const SIGN_UP_PATH = "/sign-up";

/**
 * What only the sign-in and sign-up cards add to the shared Clerk theme (applied on
 * `ClerkProvider`, see `lib/clerkAppearance.ts`): the product's bordered card.
 */
export const authAppearance = {
  elements: {
    cardBox: "cw-auth__card",
  },
};
