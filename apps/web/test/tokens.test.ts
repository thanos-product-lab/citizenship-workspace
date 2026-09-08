import { readdirSync, readFileSync } from "node:fs";
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
const ROOT = join(process.cwd(), "../..");
const TOKENS = join(ROOT, "packages/design-system/src/tokens.css");
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


describe("every token referenced is a token that exists", () => {
  /**
   * The bug this exists for is invisible to every other kind of test.
   *
   * `fill: var(--cw-surface-subtle)` shipped in the timeline band. No such token is
   * defined. CSS does not treat that as "no fill" — an invalid `var()` computes to
   * `unset`, and `fill` is an *inherited* property whose initial value is `black`. So the
   * disputed trip's hatch painted itself on a solid black tile and became the heaviest
   * mark on the chart, outweighing the presence anchor the case turns on.
   *
   * Nothing caught it. `tsc` does not read CSS strings, the linter has no token vocabulary,
   * jsdom resolves no custom properties so the component tests saw the literal string and
   * stayed green, and a screenshot would have shown *a* mark and looked plausible. A typo
   * in a token name is only visible by comparing two files, which is what this does.
   */
  const definitions = new Set(
    [...tokens.matchAll(/(--cw-[a-z0-9-]+)\s*:/g)].map((match) => match[1]!),
  );

  /** Every `var(--cw-…)` in the app, the design system and the generated-free packages. */
  function references(): Map<string, string[]> {
    const found = new Map<string, string[]>();
    const roots = [
      join(ROOT, "apps/web/app"),
      join(ROOT, "apps/web/components"),
      join(ROOT, "apps/web/features"),
      join(ROOT, "packages/design-system/src"),
    ];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
          continue;
        }
        if (!/\.(tsx?|css)$/.test(entry.name)) continue;
        // tokens.css is the definition site; a token referencing another token there is
        // resolved by the same set and would otherwise report itself.
        if (full === TOKENS) continue;
        const text = readFileSync(full, "utf8");
        for (const match of text.matchAll(/var\(\s*(--cw-[a-z0-9-]+)\s*([,)])/g)) {
          // `var(--x, fallback)` is deliberate degradation, not a typo. Only the
          // no-fallback form asserts the token exists.
          if (match[2] !== ")") continue;
          const name = match[1]!;
          found.set(name, [...(found.get(name) ?? []), full.slice(ROOT.length + 1)]);
        }
      }
    };
    roots.forEach(walk);
    return found;
  }

  it("resolves every var(--cw-…) used without a fallback", () => {
    const undefinedTokens = [...references()]
      .filter(([name]) => !definitions.has(name))
      .map(([name, files]) => `${name} (${[...new Set(files)].join(", ")})`);

    expect(undefinedTokens).toEqual([]);
  });

  it("found enough references to be checking something", () => {
    // A guard on the guard: a walk that silently matched nothing would make the assertion
    // above pass forever. The repo has hundreds; the exact number is not the point.
    expect(references().size).toBeGreaterThan(30);
  });
});
