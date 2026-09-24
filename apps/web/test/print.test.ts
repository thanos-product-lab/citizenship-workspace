import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The print stylesheet's page margins (ADR-0035).
 *
 * Chrome prints its own header (the page title) and footer (the page's web address) into
 * every margin box the page leaves undeclared, box by box. The travel list printed with
 * `localhost:3000/cases/<id>/data/travel-export` at its foot, on a file meant for the Home
 * Office. Declaring all six boxes removes both; declaring only some left the rest printing,
 * which is why each box is asserted by name.
 *
 * jsdom does not print, so this reads the stylesheet. The behaviour itself was verified by
 * printing with headless Chrome and reading the PDF's text back.
 */
const CSS = readFileSync(
  join(process.cwd(), "../../packages/design-system/src/components.css"),
  "utf8",
);

function pageRule(): string {
  const start = CSS.indexOf("@page {");
  expect(start).toBeGreaterThan(-1);
  // The rule's own closing brace: nested boxes open and close inside it.
  let depth = 0;
  for (let i = start; i < CSS.length; i++) {
    if (CSS[i] === "{") depth++;
    if (CSS[i] === "}" && --depth === 0) return CSS.slice(start, i + 1);
  }
  throw new Error("unterminated @page rule");
}

describe("print page margins", () => {
  it.each(["top-left", "top-center", "top-right", "bottom-left", "bottom-center", "bottom-right"])(
    "declares the %s box, so the browser prints nothing of its own there",
    (box) => {
      expect(pageRule()).toMatch(new RegExp(`@${box}\\s*\\{[^}]*content:`));
    },
  );

  it("numbers the pages and names nothing else", () => {
    const rule = pageRule();
    expect(rule).toMatch(/counter\(page\)/);
    expect(rule).not.toMatch(/Citizenship|Workspace|url\(/);
  });
});
