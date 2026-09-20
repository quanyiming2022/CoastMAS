import { describe, expect, it } from "vitest";
import { geographicCollection } from "./result-data";
import { geometryPositions } from "./geography";

describe("geographic map boundaries", () => {
  it("supports points and lines alongside polygon result geometry", () => {
    const data = geographicCollection.parse({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [117, 31] },
          properties: {},
        },
        {
          type: "Feature",
          geometry: {
            type: "MultiLineString",
            coordinates: [
              [
                [117, 31],
                [118, 32],
              ],
            ],
          },
          properties: {},
        },
      ],
    });
    expect(
      data.features.flatMap((feature) => geometryPositions(feature.geometry)),
    ).toEqual([
      [117, 31],
      [117, 31],
      [118, 32],
    ]);
  });
  it("rejects projected coordinates presented as geographic and degenerate lines", () => {
    for (const coordinates of [
      [
        [500000, 3500000],
        [500100, 3500100],
      ],
      [[117, 31]],
    ]) {
      expect(
        geographicCollection.safeParse({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: { type: "LineString", coordinates },
              properties: {},
            },
          ],
        }).success,
      ).toBe(false);
    }
  });
});
