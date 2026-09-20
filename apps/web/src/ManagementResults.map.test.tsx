import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import ManagementResults from "./ManagementResults";
import type { GeographicCollection } from "./result-data";

vi.mock("./GeoMap", () => ({
  default: ({
    data,
    onFeatureClick,
  }: {
    data: GeographicCollection;
    onFeatureClick: (properties: Record<string, unknown>) => void;
  }) => (
    <>
      <output data-testid="map-data">{JSON.stringify(data)}</output>
      <button
        onClick={() =>
          onFeatureClick({ entity_id: "entity2", entity_version: 1 })
        }
      >
        选择地图实体2
      </button>
    </>
  ),
}));

it("links result rows and map selections using the actual pinned entity identities", async () => {
  const objects = [1, 2].map((index) => ({
    id: `object${index}`,
    node_id: "node",
    variable: "scores",
    standard_name: "assessment_scores",
    model: { id: "model", version: 1 },
    management_unit_id: `U${index}`,
    source_pointer: "/outputs/node.scores",
    values: {},
    units: {},
  }));
  const bindings = objects.map((object, index) => ({
    result_object_id: object.id,
    geographic_entity_id: `entity${index + 1}`,
    geographic_entity_version: 1,
    management_unit_id: object.management_unit_id,
  }));
  const geometries: GeographicCollection = {
    type: "FeatureCollection",
    features: bindings.map((binding) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [117, 31] },
      properties: {
        entity_id: binding.geographic_entity_id,
        entity_version: 1,
      },
    })),
  };
  render(
    <ManagementResults
      view={{
        objects,
        entity_binding: bindings,
        unbound_objects: [],
        binding_status: "BOUND",
      }}
      geometries={geometries}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "定位 U1" }));
  await waitFor(() =>
    expect(screen.getByTestId("map-data").textContent).toContain(
      '"selected":true',
    ),
  );
  const selected = JSON.parse(
    screen.getByTestId("map-data").textContent!,
  ).features.filter(
    (feature: { properties: { selected: boolean } }) =>
      feature.properties.selected,
  );
  expect(selected[0].properties.entity_id).toBe("entity1");
  fireEvent.click(screen.getByRole("button", { name: "选择地图实体2" }));
  expect(screen.getByRole("button", { name: "定位 U2" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(screen.getByRole("button", { name: "定位 U1" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
});
