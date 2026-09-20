import { expect, it } from "vitest";
import { contract, workflowContract } from "./contracts";
const workflow = {
  id: "workflow-1",
  name: "Test workflow",
  version: 1,
  scene_type: "test",
  nodes: [{ id: "node", model_id: "model", model_version: 1 }],
  edges: [],
  input_bindings: [],
  parameter_bindings: [],
  output_definition: [],
  constraints: [],
  validation_rules: [],
  execution_policy: { max_retries: 0, timeout_seconds: 60 },
};
it("validates generated contracts including nested numeric bounds and extra fields", () => {
  expect(workflowContract.safeParse(workflow).success).toBe(true);
  expect(
    workflowContract.safeParse({
      ...workflow,
      nodes: [{ id: "node", model_id: "model", model_version: 0 }],
    }).success,
  ).toBe(false);
  expect(
    workflowContract.safeParse({ ...workflow, undeclared: "field" }).success,
  ).toBe(false);
  expect(workflowContract.safeParse({ ...workflow, nodes: [] }).success).toBe(
    false,
  );
});

it("validates decomposition dependency pairs without loosening the generated contract", () => {
  const validate = contract("DecompositionRequest");
  const request = {
    name: "test",
    kind: "declared",
    dependencies: [["a", "b"]],
  };
  expect(validate.safeParse(request).success).toBe(true);
  for (const dependencies of [[["a"]], [["a", "b", "c"]], [["a", 0]]]) {
    expect(validate.safeParse({ ...request, dependencies }).success).toBe(
      false,
    );
  }
});
