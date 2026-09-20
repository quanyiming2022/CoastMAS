import { expect, it } from "vitest";
import {
  addModel,
  connectPorts,
  removeNode,
  setParameter,
  assignData,
  emptyWorkflow,
} from "./workflow-editor";

it("preserves explicit defaults and does not invent required scientific parameters", () => {
  const draft = addModel(
    emptyWorkflow("w"),
    {
      id: "model",
      version: 3,
      parameters: [
        { name: "zero", unit: "1", default: 0, required: true },
        { name: "unknown", unit: "m", default: null, required: true },
      ],
    },
    "node",
  );
  expect(draft.nodes[0]?.model_version).toBe(3);
  expect(draft.nodes[0]?.parameters).toEqual({ zero: 0 });
});
it("rejects cycles and competing input producers without changing the original draft", () => {
  let draft = emptyWorkflow("w");
  for (const id of ["a", "b"])
    draft = addModel(draft, { id: "model", version: 1, parameters: [] }, id);
  const connection = {
    source_node: "a",
    source_variable: "out",
    target_node: "b",
    target_variable: "in",
  };
  const linked = connectPorts(draft, connection);
  expect(() =>
    connectPorts(linked, {
      source_node: "b",
      source_variable: "out",
      target_node: "a",
      target_variable: "in",
    }),
  ).toThrow(/循环/);
  expect(() =>
    assignData(
      linked,
      { node_id: "b", variable: "in" },
      { id: "data", version: 1 },
    ),
  ).toThrow(/连线/);
  const bound = assignData(
    draft,
    { node_id: "b", variable: "in" },
    { id: "data", version: 1 },
  );
  expect(() => connectPorts(bound, connection)).toThrow(/来源/);
  expect(draft.edges).toEqual([]);
  expect(bound.input_bindings[0]?.status).toBe("MANUAL_REVIEW");
});
it("removes dependent edges bindings parameters and outputs when deleting a node", () => {
  let draft = addModel(
    emptyWorkflow("w"),
    { id: "model", version: 1, parameters: [] },
    "a",
  );
  draft = addModel(draft, { id: "model", version: 1, parameters: [] }, "b");
  draft = connectPorts(draft, {
    source_node: "a",
    source_variable: "out",
    target_node: "b",
    target_variable: "in",
  });
  draft = assignData(
    draft,
    { node_id: "a", variable: "in" },
    { id: "data", version: 1 },
  );
  draft = {
    ...draft,
    parameter_bindings: [{ node_id: "a", parameter: "p", value: 2 }],
    output_definition: [{ node_id: "a", variable: "out" }],
  };
  const removed = removeNode(draft, "a");
  expect(removed.nodes.map((node) => node.id)).toEqual(["b"]);
  expect([
    removed.edges,
    removed.input_bindings,
    removed.parameter_bindings,
    removed.output_definition,
  ]).toEqual([[], [], [], []]);
});
it("edits an explicit parameter without leaving conflicting parameter sources", () => {
  const draft = {
    ...addModel(
      emptyWorkflow("w"),
      { id: "model", version: 1, parameters: [] },
      "a",
    ),
    parameter_bindings: [{ node_id: "a", parameter: "p", value: 2 }],
  };
  const edited = setParameter(draft, "a", "p", 0);
  expect(edited.parameter_bindings).toEqual([]);
  expect(edited.nodes[0]?.parameters).toEqual({ p: 0 });
  expect(() => setParameter(draft, "a", "p", Infinity)).toThrow();
});
