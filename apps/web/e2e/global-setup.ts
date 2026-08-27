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

  // The most common cause, and worth naming rather than leaving to be deduced: both
  // secrets pointing at the web app. Next.js answers any unknown path with its own 404,
  // so every API assertion downstream fails in a way that looks like an API bug.
  const looksLikeTheWebApp = API_URL === WEB_URL;
  throw new Error(
    `SMOKE_API_URL (${API_URL}) answered ${url} with ${status}, not a live API.\n\n` +
      (looksLikeTheWebApp
        ? "SMOKE_API_URL is the same as SMOKE_BASE_URL. It must be the Railway API URL, " +
          "not the Vercel one — see docs/DEPLOYMENT.md §D.\n\n"
        : "Something is answering, so the host resolves — this is the wrong host, a " +
          "failed API deploy, or a redeploy that moved the URL. Check the Railway API " +
          "service, then the SMOKE_API_URL repository secret.\n\n") +
      `Body: ${body}`,
  );
}

export default globalSetup;
