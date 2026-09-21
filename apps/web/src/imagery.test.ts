import { expect, it } from "vitest";
import { imageCoordinates, imageDescription } from "./imagery";
it("orders the georeferenced image corners and rejects invalid footprints", () => {
  expect(imageCoordinates([119, 37, 120, 38])).toEqual([
    [119, 38],
    [120, 38],
    [120, 37],
    [119, 37],
  ]);
  const description = {
    bounds: [119, 37, 120, 38],
    label: "黄河口",
    attribution: "Copernicus",
    acquired_at: "2025-09-25T03:07:23Z",
  };
  expect(imageDescription.parse(description).label).toBe("黄河口");
  expect(
    imageDescription.safeParse({ ...description, bounds: [120, 37, 119, 38] })
      .success,
  ).toBe(false);
  expect(
    imageDescription.safeParse({ ...description, bounds: [119, 37, 181, 38] })
      .success,
  ).toBe(false);
});
