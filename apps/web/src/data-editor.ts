import { contract } from "./contracts";
import type { DataAssetSpec } from "./generated/contracts";
export const dataContract = contract("DataAssetSpec");
export function freshData(): DataAssetSpec {
  return {
    id: `data:${crypto.randomUUID()}`,
    name: "",
    type: "table",
    format: "CSV",
    uri: "",
    checksum: "",
    crs: null,
    vertical_datum: null,
    spatial_extent: null,
    time_start: null,
    time_end: null,
    time_resolution: null,
    variables: [],
    quality: {},
    source: "",
    license: "",
    version: 1,
  };
}
export function prepareDataRevision(
  draft: Record<string, unknown>,
  base: DataAssetSpec,
): DataAssetSpec {
  return dataContract.parse({
    ...draft,
    id: base.id,
    version: base.version + 1,
    uri: base.uri,
    checksum: base.checksum,
    quality: {
      ...(typeof base.quality.size_bytes === "number"
        ? { size_bytes: base.quality.size_bytes }
        : {}),
      validated: false,
    },
  });
}
export const newDataVariable = () => ({
  name: "",
  standard_name: "",
  description: "",
  data_type: null,
  unit: "",
  dimension: "",
  semantic_type: null,
  spatial_support: "",
  temporal_support: "",
  aggregation_type: null,
  nodata_policy: null,
  required: true,
});
