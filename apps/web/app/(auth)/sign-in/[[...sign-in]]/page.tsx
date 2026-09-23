import { SignIn } from "@clerk/nextjs";
import { StatusGlyph } from "@cw/design-system";

/**
 * The way in, in the product's own voice.
 *
 * **Clerk still does all of the signing in.** This page lays out the product around
 * Clerk's `<SignIn>` and themes it; it does not rebuild the form on Clerk's lower-level
 * hooks. Passwords, one-time codes, second factors, social providers, errors and account
 * recovery all stay Clerk's, which is the point of using it: a hand-built form would take
 * on each of those flows, and a custom authentication path is on CLAUDE.md's rejected list.
 *
 * **One `h1`, and it is Clerk's.** The card's title ("Sign in to …") is rendered by Clerk as
 * an `h1`, and it changes with each step ("Check your email", "Enter your password"), so it
 * is the heading that names what the user is doing. The introduction beside it is prose,
 * not a second top-level heading.
 *
 * **Themed with tokens, not colours.** Every value below is a `--cw-*` custom property, so
 * the card follows the light and dark themes with the rest of the product rather than
 * staying Clerk's white in both.
 */
export default function SignInPage() {
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

      <div className="cw-auth__panel">
        {/* `path` names this route as the one Clerk's later steps (password, codes)
            navigate within, so a step never falls back to Clerk's hosted page. */}
        <SignIn
          path="/sign-in"
          appearance={{
            variables: {
              colorPrimary: "var(--cw-accent)",
              // Clerk otherwise picks white, which fails contrast on the dark theme's light
              // accent. The token is dark text there, white in the light theme.
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
            elements: {
              cardBox: "cw-auth__card",
            },
          }}
        />
      </div>
    </main>
  );
}
