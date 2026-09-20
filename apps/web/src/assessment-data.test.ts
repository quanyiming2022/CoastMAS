import { expect, it } from "vitest";
import { assessmentGroups } from "./assessment-data";
import type { ResultObject } from "./generated/contracts";

function score(
  id: string,
  unit: string,
  years: number[] | null,
  scores: number[],
): ResultObject {
  return {
    id,
    node_id: "assessment",
    variable: "scores",
    standard_name: "assessment_scores",
    model: { id: "model", version: 1 },
    management_unit_id: unit,
    source_pointer: "/outputs/assessment.scores",
    values: { years, scores, classes: scores.map(() => 1) },
    units: { scores: "1", classes: "1", years: "year" },
  };
}
it("keeps irregular time coordinates, zero scores and management identities aligned", () => {
  const groups = assessmentGroups([
    score("a", "U2", [2020, 2021, 2025], [0, 0.2, 0.8]),
    score("b", "U1", [2020, 2021, 2025], [0.4, 0.5, 0.7]),
  ]);
  expect(groups[0]!.years).toEqual([2020, 2021, 2025]);
  expect(groups[0]!.series.map((item) => item.unitId)).toEqual(["U2", "U1"]);
  expect(groups[0]!.series[0]!.scores).toEqual([0, 0.2, 0.8]);
  expect(assessmentGroups([score("s", "U1", null, [0])])[0]!.years).toBeNull();
});
it("refuses incompatible time alignment instead of plotting plausible but wrong series", () => {
  expect(() =>
    assessmentGroups([score("a", "U1", [2020, 2021], [0.2])]),
  ).toThrow();
  expect(() =>
    assessmentGroups([score("a", "U1", [2021, 2020], [0.2, 0.3])]),
  ).toThrow();
  expect(() =>
    assessmentGroups([
      score("a", "U1", [2020, 2021], [0.2, 0.3]),
      score("b", "U2", [2020, 2025], [0.2, 0.4]),
    ]),
  ).toThrow();
  expect(() =>
    assessmentGroups([score("a", "U1", null, [0.2, 0.3])]),
  ).toThrow();
});
