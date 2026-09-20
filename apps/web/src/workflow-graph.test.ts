import { expect, it } from "vitest";
import { graphForWorkflow } from "./workflow-graph";
import { workflowContract } from "./contracts";
const workflow = workflowContract.parse({
  id: "w",
  version: 1,
  name: "Graph",
  scene_type: "test",
  nodes: [
    { id: "a", model_id: "m1", model_version: 1 },
    { id: "b", model_id: "m2", model_version: 1 },
  ],
  edges: [
    {
      source_node: "a",
      source_variable: "out",
      target_node: "b",
      target_variable: "input",
    },
  ],
  input_bindings: [],
  parameter_bindings: [],
  output_definition: [{ node_id: "b", variable: "result" }],
  constraints: [],
  validation_rules: [],
  execution_policy: { timeout_seconds: 60, max_retries: 0 },
});
it("ties validation errors to the affected node and incoming connection", () => {
  const graph = graphForWorkflow(workflow, [
    {
      code: "UNIT_INCOMPATIBLE",
      message: "unit mismatch",
      node_id: "b",
      variable: "input",
    },
  ]);
  expect(graph.nodes.find((node) => node.id === "b")?.className).toBe(
    "graph-error",
  );
  expect(graph.nodes.find((node) => node.id === "a")?.className).toBe("");
  expect(
    graph.edges.find((edge) => edge.source === "a" && edge.target === "b")
      ?.className,
  ).toBe("graph-error");
  expect(
    graph.nodes.find((node) => node.type === "output")?.data.label,
  ).toContain("result");
  expect(
    graph.nodes.find((node) => node.id === "b")?.position.x,
  ).toBeGreaterThan(
    graph.nodes.find((node) => node.id === "a")?.position.x ?? 0,
  );
});
