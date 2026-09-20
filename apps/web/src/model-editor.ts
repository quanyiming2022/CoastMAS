import schema from "../contracts.schema.json";
import { modelContract } from "./contracts";
import type { ModelSpec } from "./generated/contracts";

export function freshModel(owner: string, now: string): ModelSpec {
  return {
    id: `model:${crypto.randomUUID()}`,
    name: "",
    display_name: "",
    version: 1,
    model_type: "EXTERNAL",
    description: "",
    capabilities: [],
    scientific_domain: [],
    inputs: [],
    outputs: [],
    parameters: [],
    spatial_scale: { minimum: null, maximum: null, unit: "" },
    temporal_scale: { minimum: null, maximum: null, unit: "" },
    supported_geometry: [],
    supported_crs: [],
    runtime_type: "metadata",
    runtime_config: {},
    constraints: [],
    validation_status: "UNVALIDATED",
    validation_metrics: {},
    references: [],
    owner,
    license: "",
    created_at: now,
    updated_at: now,
    enabled: true,
    execution_status: "NOT_EXECUTABLE",
  };
}
export function prepareModelRevision(
  draft: Record<string, unknown> | ModelSpec,
  base: ModelSpec | null,
  now: string,
): ModelSpec {
  return modelContract.parse({
    ...draft,
    id: base?.id ?? draft.id,
    version: base ? base.version + 1 : 1,
    owner: base?.owner ?? draft.owner,
    created_at: base?.created_at ?? draft.created_at,
    updated_at: now,
    validation_status: "UNVALIDATED",
    execution_status: "NOT_EXECUTABLE",
    validation_metrics: {},
  });
}

export const modelFieldOptions: Record<string, readonly string[]> = {
  data_type: schema.$defs.VariableSpec.properties.data_type.enum,
  semantic_type: schema.$defs.VariableSpec.properties.semantic_type.enum,
  aggregation_type: schema.$defs.VariableSpec.properties.aggregation_type.enum,
  nodata_policy: schema.$defs.VariableSpec.properties.nodata_policy.enum,
  operator: schema.$defs.ConstraintSpec.properties.operator.enum,
};

export const modelTypes = schema.$defs.ModelType.enum;
