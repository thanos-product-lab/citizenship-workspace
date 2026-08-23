import { describe, expect, it } from "vitest";

import { CASE_DESTINATIONS, activeSegment, destinationHref } from "./destinations";

const CASE = "c1";

describe("case destinations", () => {
  it("offers every destination that has something behind it, in argument order", () => {
    // Each entry arrived with its backend module: Issues at M6, Timeline at M5, Evidence
    // at M7. A destination leading to an empty room is a promise the product cannot keep,
    // so this list is pinned and fails the moment one is added ahead of its milestone.
    //
    // The order is the order of the argument: here is what you told us (Timeline), here
    // is what follows from it (Requirements), here is what you gave us in support
    // (Evidence), here is what needs attention (Issues), here is where you change it.
    expect(CASE_DESTINATIONS.map((d) => d.label)).toEqual([
      "Overview",
      "Timeline",
      "Requirements",
      "Evidence",
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
    // `evidence` was this test's example of an unknown segment until M7 made it real,
    // which is the list being pinned working as intended. `preparation` is the next
    // destination in the IA brief with no module behind it.
    expect(activeSegment("/cases/c1/preparation", CASE)).toBeNull();
  });

  it("marks Evidence current on its own page", () => {
    expect(activeSegment("/cases/c1/evidence", CASE)).toBe("evidence");
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
