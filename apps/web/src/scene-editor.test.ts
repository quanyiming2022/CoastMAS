import { expect, it } from "vitest";
import { aoiFromUpload, closeDrawing, toggleReference } from "./scene-editor";

it("accepts a single declared geographic polygon and rejects collections or non-area geometry", () => {
  const geometry = {
    type: "Polygon",
    coordinates: [
      [
        [117, 31],
        [118, 31],
        [118, 32],
        [117, 31],
      ],
    ],
  };
  expect(aoiFromUpload({ type: "Feature", geometry, properties: {} })).toEqual(
    geometry,
  );
  expect(() =>
    aoiFromUpload({ type: "FeatureCollection", features: [] }),
  ).toThrow();
  expect(() =>
    aoiFromUpload({ type: "Point", coordinates: [117, 31] }),
  ).toThrow();
  expect(() =>
    aoiFromUpload({
      ...geometry,
      coordinates: [
        [
          [0, 0],
          [1, 0],
          [1, 1],
          [2, 0],
        ],
      ],
    }),
  ).toThrow();
});
it("closes an explicit drawing without fabricating vertices", () => {
  expect(() =>
    closeDrawing([
      [1, 1],
      [2, 1],
    ]),
  ).toThrow();
  expect(
    closeDrawing([
      [1, 1],
      [2, 1],
      [2, 2],
    ]),
  ).toEqual({
    type: "Polygon",
    coordinates: [
      [
        [1, 1],
        [2, 1],
        [2, 2],
        [1, 1],
      ],
    ],
  });
});
it("replaces the selected version of an identity and removes only the requested identity", () => {
  const old = [
    { id: "a", version: 1 },
    { id: "b", version: 2 },
  ];
  expect(toggleReference(old, { id: "a", version: 3 }, true)).toEqual([
    { id: "b", version: 2 },
    { id: "a", version: 3 },
  ]);
  expect(toggleReference(old, { id: "a", version: 1 }, false)).toEqual([
    { id: "b", version: 2 },
  ]);
  expect(old).toHaveLength(2);
});
