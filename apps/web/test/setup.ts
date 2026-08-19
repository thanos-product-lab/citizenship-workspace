import "@testing-library/jest-dom/vitest";

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
