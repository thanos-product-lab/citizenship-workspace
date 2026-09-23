import "@testing-library/jest-dom/vitest";

import { toHaveNoViolations } from "jest-axe";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, expect, vi } from "vitest";

/**
 * Clerk's account menu, replaced by a placeholder. The real one needs a `ClerkProvider`
 * and a Clerk instance, and no component test is about Clerk's menu; the case header,
 * which renders it on every case page, is. Only `UserButton` is replaced: every other
 * export stays real, so a test that mocks Clerk itself (`lib/api.test.ts`) still can.
 */
vi.mock("@clerk/nextjs", async (importOriginal) => {
  // The placeholder keeps the compound API (`UserButton.MenuItems`, `UserButton.Action`)
  // so the account menu renders; its custom items are plain buttons a test can press.
  const UserButton = Object.assign(
    ({ children }: { children?: ReactNode }) =>
      createElement("div", { "data-testid": "user-button" }, children),
    {
      MenuItems: ({ children }: { children?: ReactNode }) => createElement("div", null, children),
      Action: ({ label, onClick }: { label: string; onClick?: () => void }) =>
        onClick ? createElement("button", { type: "button", onClick }, label) : null,
      // A custom account page is rendered in place, so a test can reach what it contains.
      UserProfilePage: ({ label, children }: { label: string; children?: ReactNode }) =>
        createElement("section", { "aria-label": `${label} page` }, children),
    },
  );
  return {
    ...(await importOriginal<typeof import("@clerk/nextjs")>()),
    UserButton,
  };
});

/**
 * `expect(await axe(container)).toHaveNoViolations()`.
 *
 * **A floor, not the pass.** Automated rules catch on the order of a third of WCAG
 * failures — they find a missing accessible name and cannot find a name that is wrong, a
 * focus order that makes no sense, a live region that announces at the wrong moment, or a
 * status distinguished only by hue. Every defect the accessibility reviews in this project
 * actually found was of the second kind. This is here to stop the mechanical ones reaching
 * a human reviewer, so the human time goes where it is the only thing that works: the
 * keyboard pass and the greyscale check.
 *
 * And it is scoped to a *component*, not a page. These destinations render an `<h2>` as
 * their top heading because the `<h1>` belongs to the route layout above them, so a
 * component-level run cannot see document-wide heading order, landmark uniqueness, or a
 * duplicate id contributed by a sibling. Those need the page, which means Playwright —
 * recorded here rather than implied away, because a green matcher is otherwise easy to
 * read as more coverage than it is.
 */
expect.extend(toHaveNoViolations);

/**
 * jsdom implements no layout, so it has no `scrollIntoView`. Calling it is correct in the
 * browser and throws here, which would make a component that deep-links to a heading fail
 * for a reason that has nothing to do with its behaviour.
 *
 * Stubbed rather than guarded in the component: a `typeof === "function"` check in
 * production code to accommodate the test environment inverts which one is authoritative.
 */
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function scrollIntoView() {};
}

/**
 * jsdom has no `matchMedia` either. The Appearance page asks it which scheme the device
 * prefers, and it renders inside the account menu on every case page, so without this every
 * header test failed for a reason unrelated to what it tests. Stubbed here for the same
 * reason as `scrollIntoView`: a light-scheme device, with listeners that never fire. A test
 * that cares about the scheme replaces it.
 */
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}


/**
 * A React console error fails the test that produced it.
 *
 * These are how React reports the mistakes that a passing assertion cannot: `flushSync`
 * from a lifecycle method, an update on an unmounted component, a key collision, an
 * invalid nesting. The suite went green on exactly one of those — a `flushSync` inside a
 * `useEffect` in the date simulator — while the browser console showed it on the first
 * click. Silence in jsdom is not evidence, so the errors are made loud here instead.
 *
 * Deliberately errors only. React warnings include deprecations from libraries this
 * project does not control, and a guard that has to be suppressed is a guard nobody
 * keeps.
 */
const consoleError = console.error;

beforeEach(() => {
  console.error = (...args: unknown[]) => {
    consoleError(...args);
    throw new Error(`console.error during test: ${String(args[0])}`);
  };
});

afterEach(() => {
  // Restores this one function, not every mock. `vi.restoreAllMocks()` here would also
  // tear down spies the test files install for their own assertions — it silently broke
  // `RequirementsList`'s `scrollIntoView` spy the first time this guard was written.
  console.error = consoleError;
});
