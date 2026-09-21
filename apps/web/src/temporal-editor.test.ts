import { describe, expect, it } from "vitest";
import { observationValue } from "./temporal-editor";

describe("temporal observation entry", () => {
  it("preserves unknown values separately from a real zero", () => {
    expect(observationValue("")).toBeNull();
    expect(observationValue("  ")).toBeNull();
    expect(observationValue("0")).toBe(0);
    expect(observationValue("-2.5")).toBe(-2.5);
  });
  it("rejects non-finite and invalid entries", () => {
    for (const value of ["NaN", "Infinity", "bad", "1e999"])
      expect(() => observationValue(value)).toThrow();
  });
});
