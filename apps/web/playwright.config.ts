import { defineConfig, devices } from "@playwright/test";

import { WEB_URL } from "./e2e/target";

export default defineConfig({
  testDir: "./e2e",
  // Fails once, by name, when the smoke is pointed at something that is not this API —
  // rather than letting every API assertion report a 404 nobody can interpret.
  globalSetup: "./e2e/global-setup.ts",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  retries: process.env["CI"] ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: WEB_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
