import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Token assertions that only the stylesheet can answer.
 *
 * jsdom resolves no custom properties from an external stylesheet, so a component test
 * cannot tell `var(--cw-shell-tint)` from `var(--cw-surface-sunken)` — both render as the
 * literal string, and swapping one for the other leaves every rendering test green. These
 * read the CSS itself instead. A weaker claim than "the band is visible", but it is the
 * claim this environment can make, and it catches the substitution.
 *
 * Lives here rather than beside the tokens because `@cw/design-system` has no test runner
 * and adding one for three assertions is a larger change than the assertions are worth.
 */
const TOKENS = join(process.cwd(), "../../packages/design-system/src/tokens.css");
const tokens = readFileSync(TOKENS, "utf8");

/** What each role resolves to, per theme block, in source order. */
function valuesOf(role: string): string[] {
  return [...tokens.matchAll(new RegExp(`--${role}:\\s*([^;]+);`, "g"))].map((match) =>
    match[1]!.trim(),
  );
}

describe("shell tint", () => {
  it("is defined in every theme", () => {
    // `:root`, the `prefers-color-scheme: dark` block, and the `[data-theme="dark"]`
    // block. A token missing from the third is invisible only to users who chose dark
    // explicitly, which is the hardest variant to notice.
    expect(valuesOf("cw-shell-tint")).toHaveLength(3);
  });

  it("differs from the page background in every theme", () => {
    // The whole point of the tint is separating persistent case context from page
    // content. A tint equal to the canvas separates nothing.
    const bg = valuesOf("cw-bg");
    const tint = valuesOf("cw-shell-tint");
    expect(bg).toHaveLength(3);
    bg.forEach((value, index) => expect(tint[index]).not.toBe(value));
  });

  it("is not surface-sunken, which equals the background in dark mode", () => {
    // The trap this token exists for. `--cw-surface-sunken` is the obvious choice and is
    // identical to `--cw-bg` in both dark blocks, so a shell tinted with it would be
    // invisible in exactly the theme where the separation is hardest to see.
    const sunken = valuesOf("cw-surface-sunken");
    const bg = valuesOf("cw-bg");
    expect(sunken[1]).toBe(bg[1]);
    expect(sunken[2]).toBe(bg[2]);
  });
});
