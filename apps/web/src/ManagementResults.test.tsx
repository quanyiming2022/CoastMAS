import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import ManagementResults from "./ManagementResults";
import type { ResultView } from "./generated/contracts";

it("keeps unmatched management results visible and shows the pinned entity version", () => {
  const object = {
    id: "object-1",
    node_id: "stats",
    variable: "statistics",
    standard_name: "coastal_management_statistics",
    model: { id: "model", version: 2 },
    management_unit_id: "U1",
    source_pointer: "/outputs/stats.statistics/units/U1",
    values: { inundated_area_m2: 0 },
    units: { inundated_area_m2: "m**2" },
  };
  const view: ResultView = {
    objects: [object, { ...object, id: "object-2", management_unit_id: "U2" }],
    entity_binding: [
      {
        result_object_id: "object-1",
        geographic_entity_id: "entity-old",
        geographic_entity_version: 3,
        management_unit_id: "U1",
      },
    ],
    unbound_objects: ["object-2"],
    binding_status: "PARTIAL",
  };
  render(<ManagementResults view={view} />);
  expect(screen.getByText("部分绑定")).toBeInTheDocument();
  const rows = screen.getAllByRole("row");
  expect(within(rows[1]!).getByText("entity-old · v3")).toBeInTheDocument();
  expect(within(rows[1]!).getByText("0 m**2")).toBeInTheDocument();
  expect(within(rows[2]!).getByText("未绑定地理实体")).toBeInTheDocument();
  expect(within(rows[2]!).getByText("U2")).toBeInTheDocument();
});
