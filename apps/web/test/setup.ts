import "@testing-library/jest-dom/vitest";

import { afterEach, beforeEach } from "vitest";

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
