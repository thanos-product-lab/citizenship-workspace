import { describe, expect, it } from "vitest";

import { countryCodeFor } from "./countries";

describe("countryCodeFor", () => {
  it("maps an exact country name to its ISO code", () => {
    expect(countryCodeFor("Spain")).toBe("ES");
    expect(countryCodeFor("United Kingdom")).toBe("GB");
  });

  it("is case- and whitespace-insensitive", () => {
    expect(countryCodeFor("  spain ")).toBe("ES");
    expect(countryCodeFor("UNITED STATES")).toBe("US");
  });

  it("returns null for a free-text label that isn't a country", () => {
    expect(countryCodeFor("Barcelona")).toBeNull();
    expect(countryCodeFor("Work trip")).toBeNull();
    expect(countryCodeFor("")).toBeNull();
  });
});
