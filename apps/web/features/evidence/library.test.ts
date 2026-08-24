import { describe, expect, it } from "vitest";

import {
  IN_FLIGHT_PROCESSING_STATES,
  POLL_INTERVAL_MS,
  SETTLE_WINDOW_MS,
  TERMINAL_PROCESSING_STATES,
  pollInterval,
  type EvidenceItem,
} from "./library";

const NOW = Date.parse("2026-08-24T12:00:00Z");

function anItem(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: "ev-1",
    case_id: "case-1",
    category: "TRAVEL_SUPPORT",
    display_name: "A document",
    lifecycle_status: "ACTIVE",
    processing_status: "UPLOADED",
    media_type: "application/pdf",
    size_bytes: 1024,
    original_filename: "doc.pdf",
    uploaded_at: new Date(NOW - 60_000).toISOString(),
    created_at: new Date(NOW - 60_000).toISOString(),
    revision: 1,
    ...overrides,
  } as EvidenceItem;
}

describe("polling", () => {
  it("watches while a document is being worked on", () => {
    expect(pollInterval([anItem({ processing_status: "VALIDATING" })], NOW)).toBe(
      POLL_INTERVAL_MS,
    );
  });

  it("stops once every document has settled", () => {
    // The property that matters: a library of finished documents must not generate a
    // request every second and a half for as long as the tab is open.
    expect(pollInterval([anItem({ processing_status: "COMPLETED" })], NOW)).toBe(false);
    expect(pollInterval([anItem({ processing_status: "UNSUPPORTED" })], NOW)).toBe(false);
    expect(pollInterval([], NOW)).toBe(false);
  });

  it("watches a just-uploaded document, then gives up on it", () => {
    // The awkward case: UPLOADED is where a document sits both *before* validation and
    // after it passes, so "poll until it leaves UPLOADED" would never stop.
    const justNow = anItem({ uploaded_at: new Date(NOW - 1_000).toISOString() });
    expect(pollInterval([justNow], NOW)).toBe(POLL_INTERVAL_MS);

    const older = anItem({
      uploaded_at: new Date(NOW - SETTLE_WINDOW_MS - 1_000).toISOString(),
    });
    expect(pollInterval([older], NOW)).toBe(false);
  });

  it("keeps watching if any one document is still moving", () => {
    const settled = anItem({ id: "a", processing_status: "COMPLETED" });
    const moving = anItem({ id: "b", processing_status: "EXTRACTING_TEXT" });
    expect(pollInterval([settled, moving], NOW)).toBe(POLL_INTERVAL_MS);
  });

  it("treats an unknown state as settled rather than polling it forever", () => {
    // Fail toward *fewer* requests: a state this build does not know is more likely a
    // newer server than a document mid-flight, and an unbounded poll against every open
    // tab is the worse of the two mistakes. The state still renders verbatim.
    // Cast deliberately: the generated schema types this field to the Domain section
    // 14.4 union, so TypeScript already rejects an unknown state at compile time. The
    // case this guards is version skew at *runtime* — a newer API sending a state this
    // build predates — which no compile-time type can prevent.
    const older = anItem({
      processing_status: "SOMETHING_NEW" as EvidenceItem["processing_status"],
      uploaded_at: new Date(NOW - SETTLE_WINDOW_MS - 1_000).toISOString(),
    });
    expect(pollInterval([older], NOW)).toBe(false);
  });
});

describe("the state sets", () => {
  it("never calls a state both in-flight and terminal", () => {
    const overlap = [...IN_FLIGHT_PROCESSING_STATES].filter((s) =>
      TERMINAL_PROCESSING_STATES.has(s),
    );
    expect(overlap).toEqual([]);
  });

  it("leaves UPLOADED out of both, because it means two different things", () => {
    // Before validation and after it passes. The client cannot tell those apart from the
    // state alone, which is why the settle window exists.
    expect(IN_FLIGHT_PROCESSING_STATES.has("UPLOADED")).toBe(false);
    expect(TERMINAL_PROCESSING_STATES.has("UPLOADED")).toBe(false);
  });

  it("names only states the API can actually return", () => {
    // Guards against drift with Domain section 14.4: a typo here is a document polled
    // forever or dropped early, and neither shows up as a failure anywhere else.
    const domainStates = new Set([
      "UPLOADED",
      "VALIDATING",
      "EXTRACTING_TEXT",
      "ANALYSING",
      "AWAITING_CONFIRMATION",
      "COMPLETED",
      "PARTIALLY_COMPLETED",
      "FAILED",
      "UNSUPPORTED",
    ]);
    for (const state of [...IN_FLIGHT_PROCESSING_STATES, ...TERMINAL_PROCESSING_STATES]) {
      expect(domainStates.has(state)).toBe(true);
    }
  });
});
