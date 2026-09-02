import { expect, test } from "@playwright/test";

import { API_URL } from "./target";


test("web app is reachable and gates unauthenticated users", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.ok()).toBeTruthy();
  // clerkMiddleware sends an unauthenticated visitor to sign-in.
  await expect(page).toHaveURL(/sign-in/);
});

test("API is live", async ({ request }) => {
  const res = await request.get(`${API_URL}/health/live`);
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: "alive" });
});

test("API is ready, including its AI provider configuration", async ({ request }) => {
  const res = await request.get(`${API_URL}/health/ready`);
  const body = await res.json();
  // Named individually rather than asserting on `status`, so a red run says *which*
  // dependency is missing instead of "not_ready".
  expect(body.checks).toMatchObject({ database: true, redis: true, ai_provider: true });
  expect(res.status()).toBe(200);
});

/**
 * The one check that costs money, and the only one that can tell a working API key from
 * a well-formed one.
 *
 * `/health/ready` reports that a key is *present*. A revoked key, or an account with no
 * credit, passes that and fails every real document — which is exactly what the M8 spike
 * hit on its first live run (AI_SPIKE_FINDINGS §5). Configuration presence is not
 * reachability, and no amount of checking the former substitutes for one real call.
 *
 * Skipped rather than failed when SMOKE_AI_PROBE_SECRET is unset: the endpoint is disabled
 * without a secret by design, and a smoke that failed red on an intentionally-off feature
 * would train people to ignore it.
 */
test("AI provider answers a real call", async ({ request }) => {
  const secret = process.env["SMOKE_AI_PROBE_SECRET"];
  test.skip(!secret, "SMOKE_AI_PROBE_SECRET is not set; the probe endpoint is disabled");

  const res = await request.post(`${API_URL}/health/ai-probe`, {
    headers: { "X-Probe-Secret": secret as string },
  });

  // 429 means the daily spend ceiling is reached — the system working as designed, not a
  // provider failure. Treated as a pass so a busy day does not page anyone, and reported
  // so it is visible rather than silent.
  if (res.status() === 429) {
    console.warn("AI probe skipped: daily spend ceiling reached", await res.text());
    return;
  }

  expect(res.status(), await res.text()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
  expect(body.provider).toBe("openai");
  expect(body.latency_ms).toBeGreaterThan(0);
});
