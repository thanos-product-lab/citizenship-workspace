/**
 * `RequirementStatus` is where ADR-0001 either holds or quietly breaks, so these tests
 * are about the trust model rather than about markup.
 *
 * They live here rather than in `packages/design-system` only because vitest is
 * configured in this app; when the design system grows its own runner (slice 2 adds six
 * more components) they should move alongside the component.
 */

import "@testing-library/jest-dom/vitest";

import { RequirementStatus } from "@cw/design-system";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

describe("RequirementStatus", () => {
  it("renders a supported result as one badge with a text label", () => {
    render(<RequirementStatus conclusion="SUPPORTED" currency="CURRENT" />);
    expect(screen.getByText("Supported")).toBeInTheDocument();
  });

  it("renders SUPPORTED + STALE as two separate signals, not one merged state", () => {
    // The canonical ADR-0001 case: the conclusion still stands, but its inputs moved.
    render(<RequirementStatus conclusion="SUPPORTED" currency="STALE" />);
    expect(screen.getByText("Supported")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });

  it("does not alter the conclusion when the result goes stale", () => {
    // The conclusion badge must be byte-identical current vs stale. If staleness ever
    // restyles or relabels the conclusion, the two axes have been collapsed.
    const { container: current } = render(
      <RequirementStatus conclusion="NEAR_THRESHOLD" currency="CURRENT" />,
    );
    const { container: stale } = render(
      <RequirementStatus conclusion="NEAR_THRESHOLD" currency="STALE" />,
    );
    const badgeOf = (root: HTMLElement) => root.querySelector('[data-conclusion]')?.outerHTML;
    expect(badgeOf(current)).toEqual(badgeOf(stale));
  });

  it("shows no currency badge at all when there is no result yet", () => {
    // NOT_YET_ASSESSED has a null currency. Rendering "Current" here would claim the
    // requirement had been assessed and found up to date.
    render(<RequirementStatus conclusion="NOT_YET_ASSESSED" currency={null} />);
    expect(screen.getByText("Not yet assessed")).toBeInTheDocument();
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
    expect(screen.queryByText("Stale")).not.toBeInTheDocument();
  });

  it("does not adorn a current result", () => {
    render(<RequirementStatus conclusion="SUPPORTED" currency="CURRENT" />);
    expect(screen.queryByText("Current")).not.toBeInTheDocument();
  });

  it("distinguishes near threshold from supported", () => {
    const { container: supported } = render(<RequirementStatus conclusion="SUPPORTED" />);
    const { container: near } = render(<RequirementStatus conclusion="NEAR_THRESHOLD" />);
    expect(supported.querySelector("[data-conclusion]")).toHaveAttribute(
      "data-conclusion",
      "supported",
    );
    expect(near.querySelector("[data-conclusion]")).toHaveAttribute(
      "data-conclusion",
      "near_threshold",
    );
    expect(screen.getByText("Near threshold")).toBeInTheDocument();
  });

  it("pairs every conclusion with a glyph, so colour is never the only signal", () => {
    for (const conclusion of [
      "SUPPORTED",
      "INCOMPLETE",
      "INCONSISTENT",
      "NEAR_THRESHOLD",
      "REQUIRES_JUDGEMENT",
      "PROFESSIONAL_REVIEW_RECOMMENDED",
      "NOT_CURRENTLY_SATISFIED",
      "NOT_YET_ASSESSED",
    ]) {
      const { container, unmount } = render(<RequirementStatus conclusion={conclusion} />);
      const badge = container.querySelector("[data-conclusion]");
      expect(badge?.querySelector("svg"), `${conclusion} has no glyph`).toBeTruthy();
      expect(badge?.textContent?.trim(), `${conclusion} has no label`).toBeTruthy();
      unmount();
    }
  });

  it("marks glyphs decorative so the label carries the accessible name", () => {
    const { container } = render(<RequirementStatus conclusion="SUPPORTED" currency="STALE" />);
    for (const svg of container.querySelectorAll("svg")) {
      expect(svg).toHaveAttribute("aria-hidden", "true");
    }
  });

  it("shows an unrecognised conclusion verbatim rather than guessing", () => {
    // A value this build does not know about must not be silently rendered as something
    // benign — that would be the UI inventing a conclusion.
    render(<RequirementStatus conclusion="SOMETHING_NEW" />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
    const badge = screen.getByText("SOMETHING_NEW").closest("[data-conclusion]");
    expect(badge).toHaveAttribute("data-conclusion", "unknown");
  });
});
