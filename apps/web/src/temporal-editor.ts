import type { TemporalRequest } from "./generated/contracts";
export type TemporalMethod = TemporalRequest["method"];
export const temporalMethods: Record<TemporalMethod, string> = {
  nearest: "最近观测（nearest）",
  mean: "时长加权平均（mean）",
  sum: "累计（sum）",
  min: "观测最小值（min）",
  max: "观测最大值（max）",
  interpolation: "线性插值（interpolation）",
};
export const allowedMethods: Record<
  TemporalRequest["aggregation_type"],
  TemporalMethod[]
> = {
  intensive: ["mean", "nearest", "interpolation", "min", "max"],
  extensive: ["sum"],
  instantaneous: ["nearest", "interpolation", "min", "max"],
  categorical: ["nearest"],
};
export function observationValue(value: string): number | null {
  if (!value.trim()) return null;
  const number = Number(value);
  if (!Number.isFinite(number))
    throw new Error("观测数值必须有限；缺测请留空。");
  return number;
}
