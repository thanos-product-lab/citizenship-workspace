import { describe, expect, it } from "vitest";

import { CASE_DESTINATIONS, activeSegment, destinationHref } from "./destinations";

const CASE = "c1";

describe("case destinations", () => {
  it("offers Timeline and Issues but not Evidence yet", () => {
    // Issues landed at M6 with a backend module behind it. Evidence is M7 and has none —
    // a destination leading to an empty room is a promise the product cannot keep, and
    // this fails the moment one is added early.
    expect(CASE_DESTINATIONS.map((d) => d.label)).toEqual([
      "Overview",
      "Timeline",
      "Requirements",
      "Issues",
      "Case data",
    ]);
  });

  it("builds the case root without a trailing segment", () => {
    expect(destinationHref(CASE, "")).toBe("/cases/c1");
    expect(destinationHref(CASE, "requirements")).toBe("/cases/c1/requirements");
  });

  it("marks the overview current at the case root", () => {
    expect(activeSegment("/cases/c1", CASE)).toBe("");
  });

  it("marks a destination current on its own page", () => {
    expect(activeSegment("/cases/c1/requirements", CASE)).toBe("requirements");
    expect(activeSegment("/cases/c1/data", CASE)).toBe("data");
  });

  it("marks the parent destination current on a sub-page", () => {
    // A requirement detail is *within* Requirements. Highlighting nothing there would tell
    // a screen-reader user they had left the workspace.
    expect(activeSegment("/cases/c1/requirements/residence.total_absences", CASE)).toBe(
      "requirements",
    );
  });

  it("is unaffected by a dotted or encoded requirement key", () => {
    expect(activeSegment("/cases/c1/requirements/residence.total_absences.x", CASE)).toBe(
      "requirements",
    );
    expect(activeSegment("/cases/c1/requirements/residence%2Etotal_absences", CASE)).toBe(
      "requirements",
    );
  });

  it("returns null for an unknown segment rather than guessing", () => {
    expect(activeSegment("/cases/c1/evidence", CASE)).toBeNull();
  });

  it("does not match another case whose id merely shares a prefix", () => {
    expect(activeSegment("/cases/c123/requirements", CASE)).toBeNull();
    expect(activeSegment("/cases/c1x", CASE)).toBeNull();
  });

  it("returns null outside the case entirely", () => {
    expect(activeSegment("/", CASE)).toBeNull();
    expect(activeSegment("/cases/other", CASE)).toBeNull();
  });
});
