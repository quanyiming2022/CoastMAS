import { expect, it } from "vitest";
import { basemapSource } from "./basemaps";
it("retains attribution, published tile URLs and native imagery resolution limits", () => {
  const street = basemapSource("osm", "2024-06-01");
  expect(street?.tiles).toEqual([
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  ]);
  expect(street?.attribution).toContain("OpenStreetMap");
  const imagery = basemapSource("nasa", "2024-06-01");
  expect(imagery?.tiles?.[0]).toContain(
    "2024-06-01/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
  );
  expect(imagery?.maxzoom).toBe(9);
  expect(basemapSource("none", "invalid")).toBeNull();
});
it("rejects malformed dates instead of querying a different acquisition period", () => {
  for (const date of ["2024-02-30", "2024-6-1", "../latest"])
    expect(() => basemapSource("nasa", date)).toThrow();
});
