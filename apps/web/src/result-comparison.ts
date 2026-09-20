import type { ResultView, VersionReference } from "./generated/contracts";
export interface ComparedValue {
  value: unknown;
  unit: string | null;
  model: VersionReference;
  objectId: string;
}
export interface ComparisonRow {
  id: string;
  nodeId: string;
  variable: string;
  standardName: string;
  managementUnit: string | null;
  metric: string;
  left: ComparedValue | null;
  right: ComparedValue | null;
  sameUnit: boolean;
}
export function comparisonRows(
  left: ResultView,
  right: ResultView,
): ComparisonRow[] {
  const rows = new Map<string, ComparisonRow>();
  for (const [side, view] of [
    ["left", left],
    ["right", right],
  ] as const) {
    for (const object of view.objects) {
      for (const [metric, value] of Object.entries(object.values ?? {})) {
        const id = JSON.stringify([
          object.node_id,
          object.variable,
          object.standard_name,
          object.management_unit_id,
          metric,
        ]);
        const row = rows.get(id) ?? {
          id,
          nodeId: object.node_id,
          variable: object.variable,
          standardName: object.standard_name,
          managementUnit: object.management_unit_id,
          metric,
          left: null,
          right: null,
          sameUnit: false,
        };
        if (row[side])
          throw new Error("结果存在重复的计算来源与管理指标，无法唯一对照");
        row[side] = {
          value,
          unit: object.units?.[metric] ?? null,
          model: object.model,
          objectId: object.id,
        };
        row.sameUnit =
          row.left?.unit != null && row.left.unit === row.right?.unit;
        rows.set(id, row);
      }
    }
  }
  return [...rows.values()];
}
