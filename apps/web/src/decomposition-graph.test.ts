import { expect, it } from "vitest";
import { decompositionGraph } from "./decomposition-graph";
import type { ModelDecomposition } from "./generated/contracts";
const result: ModelDecomposition = {
  model_name: "model",
  mode: "WHITE_BOX",
  review_required: true,
  executable: false,
  warnings: [],
  cli_arguments: {},
  components: [
    { id: "post", stage: "postprocess", atomic: false },
    { id: "compute", stage: "compute", atomic: false },
    { id: "pre", stage: "preprocess", atomic: false },
  ],
  dependencies: [
    ["pre", "compute"],
    ["compute", "post"],
  ],
};
it("positions the actual dependency order even when source components are listed backwards", () => {
  const graph = decompositionGraph(result);
  const position = (id: string) =>
    graph.nodes.find((node) => node.id === id)!.position.x;
  expect(position("pre")).toBeLessThan(position("compute"));
  expect(position("compute")).toBeLessThan(position("post"));
  expect(graph.edges.map((edge) => [edge.source, edge.target])).toEqual(
    result.dependencies,
  );
});
it("rejects a cyclic display graph instead of showing an apparently valid pipeline", () => {
  expect(() =>
    decompositionGraph({
      ...result,
      dependencies: [...result.dependencies, ["post", "pre"]],
    }),
  ).toThrow();
});
