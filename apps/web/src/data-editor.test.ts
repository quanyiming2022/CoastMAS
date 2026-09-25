import { expect, it } from "vitest";
import { freshData, prepareDataRevision } from "./data-editor";
import { contract } from "./contracts";
it("starts with unknown scientific metadata and requires explicit provenance", () => {
  const fresh = freshData();
  expect(fresh.crs).toBeNull();
  expect(fresh.spatial_extent).toBeNull();
  expect(fresh.variables).toEqual([]);
  expect(contract("DataAssetSpec").safeParse(fresh).success).toBe(false);
});
it("preserves immutable file identity and size while revoking edited quality approval", () => {
  const base = {
    ...freshData(),
    name: "Measured table",
    source: "survey",
    license: "CC0",
    uri: "s3://private/data",
    checksum: "a".repeat(64),
    quality: { validated: true, size_bytes: 12, row_count: 2 },
    version: 3,
  };
  const revision = prepareDataRevision(
    {
      ...base,
      id: "spoof",
      checksum: "b".repeat(64),
      uri: "https://other.invalid",
      quality: { validated: true, size_bytes: 1 },
      name: "Revised",
    },
    base,
  );
  expect(revision.id).toBe(base.id);
  expect(revision.uri).toBe(base.uri);
  expect(revision.checksum).toBe(base.checksum);
  expect(revision.quality).toEqual({ size_bytes: 12, validated: false });
  expect(revision.version).toBe(4);
});
it("keeps intake provenance when adding scientific mappings, without retaining validation", () => {
  const base = {
    ...freshData(),
    name: "Raster",
    source: "User source",
    license: "Noncommercial",
    uri: "s3://private/data",
    checksum: "a".repeat(64),
    quality: {
      size_bytes: 99,
      declarations: { year: 2022 },
      file_facts: { unit: null },
      validated: true,
    },
  };
  const revision = prepareDataRevision(
    { ...base, quality: { declarations: { year: 1900 } } },
    base,
  );
  expect(revision.quality.declarations).toEqual({ year: 2022 });
  expect(revision.quality.file_facts).toEqual({ unit: null });
  expect(revision.quality.validated).toBe(false);
});
