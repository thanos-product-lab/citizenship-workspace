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

import { API_URL } from "./target";

const CASE_ID = process.env["E2E_CASE_ID"];

// A case id that is well-formed but certainly not the visitor's, for boundary checks.
const FOREIGN_CASE = "00000000-0000-4000-8000-000000000000";

test.describe("the M4 surfaces are not public", () => {
  for (const path of [
    `/cases/${FOREIGN_CASE}`,
    // Every destination the workspace split introduced. A new route tree is a new chance
    // to fall outside the middleware matcher, so each one is pinned here explicitly.
    `/cases/${FOREIGN_CASE}/requirements`,
    `/cases/${FOREIGN_CASE}/data`,
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

    // The overview leads with what the reader has to do, not with the phase name: the
    // heading is the readiness headline, and the phase stays a quiet chip by the title.
    await expect(page.getByRole("heading", { level: 2 }).first()).toContainText(
      /needs your attention/i,
    );
    await expect(page.getByRole("heading", { level: 2 }).first()).not.toContainText(
      /resolving issues/i,
    );
    await expect(page.getByRole("list", { name: "Requirements by state" })).toBeVisible();

    // No readiness score reaches the screen, in any of its forms (CLAUDE.md §2.6). The
    // ratio check matters as much as the percentage: "4 / 5" is the same measure arrived
    // at sideways, and it renders a failed conclusion as a missing one.
    await expect(page.locator("body")).not.toContainText("%");
    await expect(page.locator("main")).not.toContainText(/\d+\s*\/\s*\d+/);

    // Overview is a summary, not the whole product: the requirements themselves and the
    // editable inputs live on their own destinations.
    await expect(page.getByRole("link", { name: "Total absences" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /delete case/i })).toHaveCount(0);

    // The assessment rows state each group in counts of named states, never a verdict of
    // the group's own and never a fraction.
    await expect(page.getByText("1 not currently satisfied · 1 near threshold · 3 supported"))
      .toBeVisible();
    await expect(page.getByText("2 not yet assessed").first()).toBeVisible();

    // Into the assessment workspace by deep link, which has to land on the group itself:
    // the fragment resolves at navigation time, before this list has fetched, so an
    // unhandled one leaves the reader at the top of a long page instead.
    await page.getByRole("link", { name: "Residence" }).click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/requirements#group-RESIDENCE$`));
    await expect(page).toHaveTitle(/Requirements/);
    await expect(page.locator("#group-RESIDENCE")).toBeFocused();
    await expect(page.locator("#group-RESIDENCE")).toBeInViewport();

    // A sub-page of Requirements keeps the parent destination marked current.
    await expect(
      page.getByRole("navigation", { name: "Case navigation" })
        .getByRole("link", { name: "Requirements" }),
    ).toHaveAttribute("aria-current", "page");

    await page.getByRole("link", { name: "Total absences" }).click();
    await expect(page).toHaveTitle(/Total absences/);

    // A requirement is a sub-page of Requirements, so the nav still marks it current —
    // the reader has not left the workspace.
    await expect(
      page.getByRole("navigation", { name: "Case navigation" })
        .getByRole("link", { name: "Requirements" }),
    ).toHaveAttribute("aria-current", "page");

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

    // Up one level, to the requirement's parent destination — not to the case root.
    await page.getByRole("link", { name: /Back to requirements/ }).click();
    await expect(page).toHaveURL(new RegExp(`/cases/${CASE_ID}/requirements$`));
  });

  test("shows a stale conclusion, then the figure that changed after recalculating", async ({
    page,
  }) => {
    // Inputs are edited under Case data.
    await page.goto(`/cases/${CASE_ID}/data`);

    // Change an input: the trip departing 4 May 2026 returns a day later.
    await page.getByRole("button", { name: "Edit" }).first().click();
    const returnDate = page.getByLabel(/return/i);
    await returnDate.fill("2026-05-11");
    await page.getByRole("button", { name: /save|update/i }).click();

    // Staleness is stated *here*, on the destination where the edit was made. If it only
    // appeared on Overview, the split would have separated staleness from its own cause.
    await expect(page.getByText(/have not been rechecked/)).toBeVisible();

    // Recalculate is a case-level command, available from every destination.
    await page.getByRole("button", { name: "Recalculate" }).click();
    await expect(page.getByText(/have not been rechecked/)).toBeHidden();

    // The change becomes legible as a figure — both runs conclude NEAR_THRESHOLD, so the
    // conclusions alone would read as nothing having happened.
    await page.goto(`/cases/${CASE_ID}/requirements`);
    await expect(page.getByText(/conclusions are stale/)).toHaveCount(0);
    await page.getByRole("link", { name: "Total absences" }).click();
    await expect(page.getByRole("heading", { name: "Assessment history" })).toBeVisible();
    await expect(page.getByText("changed to")).toBeVisible();
    await expect(page.locator(".cw-change__before")).toHaveText("439 days");
    await expect(page.locator(".cw-change__after")).toHaveText("440 days");
    // The superseded run is still inspectable, not overwritten.
    await expect(page.getByText("Superseded")).toBeVisible();
  });
});
