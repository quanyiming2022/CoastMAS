import { expect, it } from "vitest";
import { geographicCollection, coastalStatistics } from "./result-data";
it("accepts geographic polygons and rejects invalid geographic coordinates", () => {
  const polygon = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [117, 31],
              [117.01, 31],
              [117.01, 31.01],
              [117, 31],
            ],
          ],
        },
      },
    ],
  };
  expect(geographicCollection.safeParse(polygon).success).toBe(true);
  const projected = structuredClone(polygon);
  projected.features[0]!.geometry.coordinates[0]![0] = [500000, 3500000];
  expect(geographicCollection.safeParse(projected).success).toBe(false);
});
it("preserves unknown-area and population assumptions with measured totals", () => {
  const value = {
    inundated_area_m2: 80000,
    estimated_affected_population: 320,
    unknown_area_m2: 100,
    population_assumption: "uniform within each management unit",
    method: "terrain-connectivity screening, not hydrodynamics",
    units: {
      U1: {
        inundated_area_m2: 40000,
        estimated_population: 120,
        unknown_area_m2: 100,
      },
    },
  };
  expect(
    coastalStatistics.safeParse({ ...value, method: "hydrodynamic model" })
      .success,
  ).toBe(false);
  expect(coastalStatistics.parse(value).unknown_area_m2).toBe(100);
  expect(
    coastalStatistics.safeParse({ ...value, population_assumption: undefined })
      .success,
  ).toBe(false);
});
