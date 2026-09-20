import { z } from "zod";
import { contract } from "./contracts";
import { geographicCollection } from "./result-data";
export const payloadSchema = z.object({
  outputs: z.record(z.string(), z.unknown()),
  node_outputs: z.record(z.string(), z.unknown()),
  executed_nodes: z.array(z.string()),
  elapsed_seconds: z.number().nonnegative(),
  llm_calls: z.number().int().nonnegative(),
  run_manifest: contract("RunManifest"),
  input_fingerprint: z.string(),
  result_view: contract("ResultView").optional(),
  result_entity_geometries: geographicCollection.optional(),
});
