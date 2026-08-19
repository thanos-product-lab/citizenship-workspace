/**
 * Where the smoke runs.
 *
 * Locally this defaults to the dev stack. In CI it must not, and the difference matters:
 * the smoke workflow exists to test the **deployed** environment, so falling back to
 * localhost there would test nothing at all.
 *
 * The specific trap this closes: GitHub Actions sets an unconfigured secret to the **empty
 * string**, not to undefined. `process.env.X ?? fallback` therefore does *not* fall back —
 * `""` is not nullish — and `baseURL` becomes `""`, so every test fails with `Invalid URL`.
 * The job reports red and says nothing about the actual cause, which is that two repository
 * secrets were never set. Failing here instead names them.
 */
function target(name: string, fallback: string): string {
  const value = process.env[name];
  // Truthiness, not nullish: an unset secret arrives as "" and must be treated as absent.
  if (value) return value;

  if (process.env["CI"]) {
    throw new Error(
      `${name} is not set.\n\n` +
        `The smoke job runs against the deployed environment, so it cannot fall back to ` +
        `localhost. Set the SMOKE_BASE_URL (web) and SMOKE_API_URL (API) repository ` +
        `secrets — see docs/DEPLOYMENT.md §D. If the app is not deployed yet, follow ` +
        `§A–C first.`,
    );
  }

  return fallback;
}

/** The web app under test. Playwright resolves relative `page.goto` paths against this. */
export const WEB_URL = target("SMOKE_BASE_URL", "http://localhost:3000");

/** The API under test. Used for direct requests that bypass the browser. */
export const API_URL = target("SMOKE_API_URL", "http://localhost:8000");
