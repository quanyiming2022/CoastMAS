import Ajv from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { z } from "zod";
import schema from "../contracts.schema.json";
import type { CoastMASContracts } from "./generated/contracts";

const ajv = new Ajv({ allErrors: true, strict: true });
addFormats(ajv);
ajv.addSchema(schema, "coastmas");
// Both the validator and TypeScript declaration are generated from the same Python source.
export function contract<K extends keyof CoastMASContracts>(
  name: K,
): z.ZodType<CoastMASContracts[K]> {
  const validate = ajv.compile<CoastMASContracts[K]>({
    $ref: `coastmas#/$defs/${name}`,
  });
  return z.custom<CoastMASContracts[K]>((value: unknown) => validate(value), {
    message: `Invalid ${name} contract`,
  });
}
export const workflowContract = contract("WorkflowSpec");
export const modelContract = contract("ModelSpec");
export const sceneContract = contract("SceneSpec");
export const planningContract = contract("PlanningArtifact");
