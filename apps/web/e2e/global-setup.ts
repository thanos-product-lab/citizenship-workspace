import { API_URL, WEB_URL } from "./target";

/**
 * Confirm the smoke is pointed at the right things before any test runs.
 *
 * `target.ts` already refuses to *guess* a URL in CI. This closes the next gap along: a URL
 * that is set, resolves, and answers — with something that is not this API.
 *
 * Without it the symptom is four unrelated-looking failures. `/health/live` returns 404
 * where 200 was expected, and three auth checks return 404 where 401 was expected, so the
 * run reads as "the API forgot its health endpoint and stopped authenticating" when the
 * actual fact is that `SMOKE_API_URL` is not this API. That cost a real diagnosis; a
 * preflight that names it costs one request.
 *
 * It checks the *shape* of the response, not just the status. A 200 from something else
 * would be worse than a 404 — the auth assertions would then fail against a stranger.
 */
async function globalSetup(): Promise<void> {
  const url = `${API_URL}/health/live`;
  let status: number;
  let body: string;

  try {
    const response = await fetch(url);
    status = response.status;
    body = (await response.text()).slice(0, 200);
  } catch (cause) {
    throw new Error(
      `SMOKE_API_URL (${API_URL}) could not be reached at all.\n` +
        `Nothing answered ${url}. The API is not deployed, is asleep, or the URL is wrong.\n` +
        `See docs/DEPLOYMENT.md §D.\n\nCause: ${String(cause)}`,
    );
  }

  if (status === 200 && body.includes('"alive"')) return;

  throw new Error(
    `SMOKE_API_URL (${API_URL}) answered ${url} with ${status}, not a live API.\n\n` +
      diagnose(status, body) +
      `\n\nBody: ${body}`,
  );
}

/** Turn what answered into what to do about it. */
function diagnose(status: number, body: string): string {
  // Both secrets pointing at the web app. Next.js answers any unknown path with its own
  // 404, so every API assertion downstream fails in a way that looks like an API bug.
  if (API_URL === WEB_URL) {
    return (
      "SMOKE_API_URL is the same as SMOKE_BASE_URL. It must be the Railway API URL, not " +
      "the Vercel one — see docs/DEPLOYMENT.md §D."
    );
  }

  // Railway's edge router, which is worth recognising because its wording is opaque and
  // its meaning is specific: the hostname resolves to Railway but no application is
  // attached to it. A *crashed* service answers differently ("Application failed to
  // respond", 502), so this is not a service that is down — it is a service that is not
  // there, or a domain that has moved.
  if (body.includes('"Application not found"')) {
    return (
      "That is Railway's router saying no application is attached to this hostname — not " +
      "an API that is down. A crashed service answers 502 'Application failed to " +
      "respond'; this is a hostname with nothing behind it.\n\n" +
      "So the API service, its public domain, or the whole project is gone or renamed. " +
      "**The deployed web app is broken too**, not just this test: Vercel's " +
      "NEXT_PUBLIC_API_BASE_URL points at the same URL (docs/DEPLOYMENT.md §B.3), so a " +
      "signed-in user loading a case gets nothing. Redeploy the API service, then update " +
      "both NEXT_PUBLIC_API_BASE_URL and the SMOKE_API_URL secret if the URL changed."
    );
  }

  if (status >= 500) {
    return (
      "The host is right and the application is failing — this is a deploy or a boot " +
      "error, not a misconfigured URL. Check the Railway API service's deploy logs; a " +
      "failed pre-deploy migration fails the deploy by design (docs/DEPLOYMENT.md §A.5)."
    );
  }

  return (
    "Something is answering, so the host resolves — this is the wrong host, a failed API " +
    "deploy, or a redeploy that moved the URL. Check the Railway API service, then the " +
    "SMOKE_API_URL repository secret."
  );
}

export default globalSetup;
