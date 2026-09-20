import { expect, it } from "vitest";
import { comparisonRows } from "./result-comparison";
import type { ResultView } from "./generated/contracts";

function view(value: number, unit = "m**2", managementUnit = "U1"): ResultView {
  return {
    binding_status: "UNBOUND",
    entity_binding: [],
    unbound_objects: ["r"],
    objects: [
      {
        id: "r",
        node_id: "statistics",
        variable: "statistics",
        standard_name: "coastal_management_statistics",
        model: { id: "model", version: 1 },
        management_unit_id: managementUnit,
        source_pointer: "/outputs/statistics.statistics",
        values: { area: value },
        units: { area: unit },
      },
    ],
  };
}
it("keeps zeros, incompatible units and missing management units explicit", () => {
  const aligned = comparisonRows(view(0), view(4, "km**2"));
  expect(aligned[0]!.left?.value).toBe(0);
  expect(aligned[0]!.right?.unit).toBe("km**2");
  expect(aligned[0]!.sameUnit).toBe(false);
  const different = comparisonRows(view(0), view(4, "m**2", "U2"));
  expect(different).toHaveLength(2);
  expect(different[0]!.right).toBeNull();
  expect(different[1]!.left).toBeNull();
});
it("does not merge outputs solely because their management IDs match", () => {
  const left = view(2);
  left.objects.push({
    ...left.objects[0]!,
    id: "r2",
    node_id: "alternative",
    values: { area: 9 },
  });
  const rows = comparisonRows(left, view(3));
  expect(rows).toHaveLength(2);
  expect(rows.find((row) => row.nodeId === "alternative")!.right).toBeNull();
});
