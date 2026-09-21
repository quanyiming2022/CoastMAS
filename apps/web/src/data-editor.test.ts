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
