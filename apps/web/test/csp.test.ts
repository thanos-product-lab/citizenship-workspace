import { describe, expect, it } from "vitest";

import config from "../next.config";

/** The Content-Security-Policy header every page is served with. */
async function policy(): Promise<string> {
  const rules = await config.headers!();
  const header = rules
    .flatMap((rule) => rule.headers)
    .find((h) => h.key === "Content-Security-Policy");
  expect(header).toBeDefined();
  return header!.value;
}

function frameSrc(csp: string): string[] {
  const directive = csp.split(";").map((d) => d.trim()).find((d) => d.startsWith("frame-src"));
  expect(directive).toBeDefined();
  return directive!.split(/\s+/).slice(1);
}

describe("the Content-Security-Policy", () => {
  it("lets Clerk's bot check load on the sign-in and sign-up pages", async () => {
    // Clerk runs Cloudflare Turnstile in an iframe from this origin. Without it the browser
    // refused the frame and sign-in stalled at the challenge.
    expect(frameSrc(await policy())).toContain("https://challenges.cloudflare.com");
  });

  it("still frames only named origins, never everything", async () => {
    const sources = frameSrc(await policy());
    expect(sources).toContain("'self'");
    expect(sources).not.toContain("*");
    expect(sources.every((s) => s === "'self'" || /^https?:\/\/[^*]+$/.test(s))).toBe(true);
  });

  it("allows no plugin content", async () => {
    expect(await policy()).toContain("object-src 'none'");
  });
});
