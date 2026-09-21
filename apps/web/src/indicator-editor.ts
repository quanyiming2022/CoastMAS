import { contract } from "./contracts";
import type {
  IndicatorDefinition,
  IndicatorFrameworkSpec,
} from "./generated/contracts";
export type FrameworkDraft = Omit<
  IndicatorFrameworkSpec,
  "indicators" | "class_breaks" | "demo"
> & {
  indicators: IndicatorDefinition[];
  class_breaks: number[];
  demo: boolean;
};
export function frameworkDraft(spec: IndicatorFrameworkSpec): FrameworkDraft {
  return {
    ...spec,
    indicators: [...spec.indicators],
    class_breaks: spec.class_breaks ?? [0.25, 0.5, 0.75],
    demo: spec.demo ?? false,
  };
}
export const frameworkContract = contract("IndicatorFrameworkSpec");
export function freshIndicator(): IndicatorDefinition {
  return {
    indicator_id: `indicator:${crypto.randomUUID()}`,
    name: "",
    category: "",
    unit: "",
    direction: "positive",
    source: { x: "" },
    formula: "x",
    normalization: { method: "fixed_minmax", lower: NaN, upper: NaN },
    weight_method: "manual",
    weight: NaN,
  };
}
export function freshFramework(): FrameworkDraft {
  return {
    id: `framework:${crypto.randomUUID()}`,
    name: "",
    version: 1,
    description: "",
    demo: false,
    spatial_support: "management_unit",
    indicators: [],
    class_breaks: [0.25, 0.5, 0.75],
  };
}
export function prepareFrameworkRevision(
  draft: FrameworkDraft,
  base: IndicatorFrameworkSpec | null,
): IndicatorFrameworkSpec {
  return frameworkContract.parse({
    ...draft,
    id: base?.id ?? draft.id,
    version: base ? base.version + 1 : 1,
  });
}
export function setWeightMethod(
  draft: FrameworkDraft,
  method: IndicatorDefinition["weight_method"],
): FrameworkDraft {
  return {
    ...draft,
    indicators: draft.indicators.map((item) => ({
      ...item,
      weight_method: method,
      weight: method === "manual" ? (item.weight ?? NaN) : null,
    })),
  };
}
