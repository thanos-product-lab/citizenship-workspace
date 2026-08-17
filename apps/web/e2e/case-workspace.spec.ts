/**
 * The M4 case-workspace journey.
 *
 * Two halves, because they need different things to be true.
 *
 * **Runs everywhere:** the M4 surfaces are not accidentally public. Every case route
 * redirects an unauthenticated visitor to sign-in, and every new API endpoint answers 401.
 * These pin the ownership boundary at both edges and need no session.
 *
 * **Needs a session:** the full walkthrough — overview → requirement detail → back, and
 * the stale → recalculate → changed-figure loop against the canonical case. Clerk protects
 * every route but `/sign-in`, so driving this requires test-user credentials. It is
 * `skip`ped rather than deleted so it runs the moment those exist:
 *
 *     E2E_CASE_ID=<seeded case id> pnpm --filter @cw/web e2e
 *
 * with an authenticated storage state configured in `playwright.config.ts`. Seed the case
 * with `just seed <your-clerk-user-id>` — and seed it *after* your last `just test-be`,
 * which truncates the case tables.
 */

import { expect, test } from "@playwright/test";

const API_URL = process.env["SMOKE_API_URL"] ?? "http://localhost:8000";
const CASE_ID = process.env["E2E_CASE_ID"];

// A case id that is well-formed but certainly not the visitor's, for boundary checks.
const FOREIGN_CASE = "00000000-0000-4000-8000-000000000000";

test.describe("the M4 surfaces are not public", () => {
  for (const path of [
    `/cases/${FOREIGN_CASE}`,
    // Dotted requirement keys: the original matcher excluded any path containing a dot.
    `/cases/${FOREIGN_CASE}/requirements/residence.total_absences`,
    // Appended static extensions: narrowing that exclusion to *known* extensions still
    // let an attacker opt out of the middleware by suffixing a segment they control.
    // These four failed on the first attempt at the fix.
    `/cases/${FOREIGN_CASE}.png`,
    `/cases/${FOREIGN_CASE}/requirements/foo.png`,
    `/cases/${FOREIGN_CASE}/requirements/residence.total_absences.png`,
    `/cases/${FOREIGN_CASE}/requirements/x.svg`,
  ]) {
    test(`${path} redirects an unauthenticated visitor to sign-in`, async ({ page }) => {
      await page.goto(path);
      await expect(page).toHaveURL(/sign-in/);
    });
  }

  for (const endpoint of [
    "overview",
    "requirements",
    "requirements/residence.total_absences",
  ]) {
    test(`GET ${endpoint} requires authentication`, async ({ request }) => {
      const res = await request.get(`${API_URL}/api/v1/cases/${FOREIGN_CASE}/${endpoint}`);
      // 401, never 200-with-empty-data: an unauthenticated read must not be answered at
      // all, and never with a shape a client could render as "nothing to report".
      expect(res.status()).toBe(401);
    });
  }
});

test.describe("the canonical case walkthrough", () => {
  test.skip(
    !CASE_ID,
    "Needs E2E_CASE_ID and an authenticated storage state — see the file header.",
  );

  test("reads the overview, opens a requirement, and traces its conclusion", async ({ page }) => {
    await page.goto(`/cases/${CASE_ID}`);

    // The overview states where the case stands, in counts of named states.
    await expect(page.getByRole("heading", { level: 2 })).toContainText(/your case/i);
    await expect(page.getByRole("list", { name: "Requirements by state" })).toBeVisible();
    // No readiness score reaches the screen (CLAUDE.md §2.6).
    await expect(page.locator("body")).not.toContainText("%");

    // Into the signature interaction.
    await page.getByRole("link", { name: "Total absences" }).click();
    await expect(page).toHaveTitle(/Total absences/);

    // The M3B oracle, on screen: 439 confirmed days against a threshold of 450.
    await expect(page.getByText("439 confirmed days against a threshold of 450")).toBeVisible();

    // Every layer of the explanation stack is a real heading (UI/UX §7.3).
    for (const layer of [
      "Why this assessment was made",
      "Facts used",
      "Travel records used",
      "Evidence used",
      "Rule used",
      "Limitations",
      "Next action",
    ]) {
      await expect(page.getByRole("heading", { name: layer, level: 2 })).toBeVisible();
    }

    // The evidence layer is present and says nothing is linked — the honest gap.
    await expect(page.getByText(/No documents are linked to these records/)).toBeVisible();
    // The guidance gap is declared, never filled.
    await expect(page.getByText(/are not recorded yet/)).toBeVisible();

    await page.getByRole("link", { name: /Back to the case/ }).click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}$`));
  });

  test("shows a stale conclusion, then the figure that changed after recalculating", async ({
    page,
  }) => {
    await page.goto(`/cases/${CASE_ID}`);

    // Change an input: the trip departing 4 May 2026 returns a day later.
    await page.getByRole("button", { name: "Edit" }).first().click();
    const returnDate = page.getByLabel(/return/i);
    await returnDate.fill("2026-05-11");
    await page.getByRole("button", { name: /save|update/i }).click();

    // Staleness surfaces at case level and on the group, without the conclusions moving.
    await expect(page.getByText(/have not been rechecked/)).toBeVisible();
    await expect(page.getByText(/conclusions are stale/)).toBeVisible();

    // Recalculate, and the change becomes legible as a figure — both runs conclude
    // NEAR_THRESHOLD, so the conclusions alone would read as nothing having happened.
    await page.getByRole("button", { name: "Recalculate" }).click();
    await expect(page.getByText(/have not been rechecked/)).toBeHidden();

    await page.getByRole("link", { name: "Total absences" }).click();
    await expect(page.getByRole("heading", { name: "Assessment history" })).toBeVisible();
    await expect(page.getByText("changed to")).toBeVisible();
    await expect(page.locator(".cw-change__before")).toHaveText("439 days");
    await expect(page.locator(".cw-change__after")).toHaveText("440 days");
    // The superseded run is still inspectable, not overwritten.
    await expect(page.getByText("Superseded")).toBeVisible();
  });
});
