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
