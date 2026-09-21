import { contract } from "./contracts";
import type { DataSourceSpec } from "./generated/contracts";
export const sourceContract = contract("DataSourceSpec");
export function freshSource(): DataSourceSpec {
  return {
    id: `source:${crypto.randomUUID()}`,
    name: "",
    version: 1,
    connector_id: "",
    kind: "http",
    output: {
      name: "",
      type: "table",
      format: "CSV",
      crs: null,
      vertical_datum: null,
      spatial_extent: null,
      time_start: null,
      time_end: null,
      time_resolution: null,
      variables: [],
      source: "",
      license: "",
    },
  };
}
export function prepareSourceRevision(
  draft: Record<string, unknown>,
  base: DataSourceSpec | null,
): DataSourceSpec {
  return sourceContract.parse({
    ...draft,
    id: base?.id ?? draft.id,
    version: base ? base.version + 1 : 1,
  });
}
