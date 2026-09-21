import { expect, it } from "vitest";
import {
  freshFramework,
  freshIndicator,
  prepareFrameworkRevision,
  setWeightMethod,
} from "./indicator-editor";
import type { IndicatorFrameworkSpec } from "./generated/contracts";
import { frameworkDraft } from "./indicator-editor";
import { contract } from "./contracts";
it("requires explicit scientific bounds and units instead of fabricated defaults", () => {
  const fresh = freshFramework();
  const indicator = freshIndicator();
  expect(indicator.unit).toBe("");
  expect(Number.isNaN(indicator.normalization.lower)).toBe(true);
  expect(
    contract("IndicatorFrameworkSpec").safeParse({
      ...fresh,
      indicators: [indicator],
    }).success,
  ).toBe(false);
});
it("pins identity and keeps meaningful zero weights while revising", () => {
  const base: IndicatorFrameworkSpec = {
    ...freshFramework(),
    name: "Test",
    description: "Synthetic",
    version: 3,
    indicators: [
      {
        ...freshIndicator(),
        name: "Height",
        category: "Resource",
        unit: "m",
        source: { x: "height" },
        normalization: { method: "fixed_minmax" as const, lower: 0, upper: 2 },
        weight: 0,
      },
    ],
  };
  const next = prepareFrameworkRevision(
    { ...frameworkDraft(base), id: "spoof", version: 400 },
    base,
  );
  expect(next.id).toBe(base.id);
  expect(next.version).toBe(4);
  expect(next.indicators[0]?.weight).toBe(0);
  const computed = setWeightMethod(frameworkDraft(base), "entropy");
  expect(computed.indicators[0]?.weight).toBeNull();
  expect(computed.indicators[0]?.weight_method).toBe("entropy");
  expect(
    Number.isNaN(setWeightMethod(computed, "manual").indicators[0]?.weight),
  ).toBe(true);
});
