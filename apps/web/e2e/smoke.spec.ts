import { expect, test } from "@playwright/test";

const API_URL = process.env["SMOKE_API_URL"] ?? "http://localhost:8000";

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
