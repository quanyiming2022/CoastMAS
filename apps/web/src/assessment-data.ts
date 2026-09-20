import { z } from "zod";
import type { ResultObject } from "./generated/contracts";

const scoreValues = z
  .object({
    years: z.array(z.number().finite()).min(1).nullable(),
    scores: z.array(z.number().min(0).max(1)).min(1),
    classes: z.array(z.number().int().nonnegative()).min(1),
  })
  .refine(
    (value) =>
      value.classes.length === value.scores.length &&
      (value.years === null
        ? value.scores.length === 1
        : value.years.length === value.scores.length &&
          value.years.every(
            (year, index) => index === 0 || year > value.years![index - 1]!,
          )),
    "评价年份、分数和等级未正确对应",
  );

export interface AssessmentGroup {
  id: string;
  label: string;
  years: number[] | null;
  series: {
    objectId: string;
    unitId: string;
    scores: number[];
    classes: number[];
  }[];
}
export function assessmentGroups(objects: ResultObject[]): AssessmentGroup[] {
  const groups = new Map<string, AssessmentGroup>();
  for (const object of objects) {
    if (object.standard_name !== "assessment_scores") continue;
    if (!object.management_unit_id || object.units?.scores !== "1")
      throw new Error("评价结果缺少管理单元或无量纲分数声明");
    const values = scoreValues.parse(object.values);
    const id = JSON.stringify([
      object.node_id,
      object.variable,
      object.model.id,
      object.model.version,
    ]);
    const group = groups.get(id) ?? {
      id,
      label: `${object.node_id} / ${object.variable} · ${object.model.id} v${object.model.version}`,
      years: values.years,
      series: [],
    };
    if (
      JSON.stringify(group.years) !== JSON.stringify(values.years) ||
      group.series.some((item) => item.unitId === object.management_unit_id)
    )
      throw new Error("同一评价输出的时间或管理单元不一致");
    group.series.push({
      objectId: object.id,
      unitId: object.management_unit_id,
      scores: values.scores,
      classes: values.classes,
    });
    groups.set(id, group);
  }
  return [...groups.values()];
}
