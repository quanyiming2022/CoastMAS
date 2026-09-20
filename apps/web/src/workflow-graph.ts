import type { Edge, Node } from "@xyflow/react";
import type { WorkflowSpec } from "./generated/contracts";
export interface ValidationIssue {
  code: string;
  message: string;
  node_id?: string | null;
  variable?: string | null;
}
export function graphForWorkflow(
  workflow: WorkflowSpec,
  issues: ValidationIssue[] = [],
): { nodes: Node[]; edges: Edge[] } {
  const levels = new Map<string, number>();
  for (const node of workflow.nodes) levels.set(node.id, 1);
  // Iteration is bounded even when an edited candidate contains a cycle; server preflight rejects it.
  for (let step = 0; step < workflow.nodes.length; step++) {
    let changed = false;
    for (const edge of workflow.edges) {
      const next = Math.min(
        workflow.nodes.length,
        (levels.get(edge.source_node) ?? 0) + 1,
      );
      if (next > (levels.get(edge.target_node) ?? 0)) {
        levels.set(edge.target_node, next);
        changed = true;
      }
    }
    if (!changed) break;
  }
  const rows = new Map<number, number>();
  const nodes: Node[] = workflow.nodes.map((node) => {
    const level = levels.get(node.id) ?? 1;
    const row = rows.get(level) ?? 0;
    rows.set(level, row + 1);
    const errors = issues.filter((issue) => issue.node_id === node.id);
    return {
      id: node.id,
      position: { x: level * 290, y: row * 170 },
      data: {
        label: `${node.kind === "transform" ? "转换" : node.kind === "validation" ? "校验" : "模型"} · ${node.id}\n${node.model_id.split(":").at(-1)} v${node.model_version}${errors.length ? "\n" + errors.map((error) => error.code).join(", ") : ""}`,
      },
      className: errors.length ? "graph-error" : "",
    };
  });
  const edges: Edge[] = workflow.edges.map((edge, index) => ({
    id: "edge-" + index,
    source: edge.source_node,
    target: edge.target_node,
    label: `${edge.source_variable} → ${edge.target_variable}`,
    className: issues.some(
      (issue) =>
        issue.node_id === edge.target_node &&
        (!issue.variable || issue.variable === edge.target_variable),
    )
      ? "graph-error"
      : "",
  }));
  const sourceIds = new Map<string, string>();
  workflow.input_bindings.forEach((binding, index) => {
    const key = binding.source.id + "@" + binding.source.version;
    let id = sourceIds.get(key);
    if (!id) {
      id = "__data-" + sourceIds.size;
      sourceIds.set(key, id);
      nodes.push({
        id,
        type: "input",
        position: { x: 0, y: (sourceIds.size - 1) * 120 },
        data: {
          label:
            "数据 · " +
            binding.source.id.split(":").at(-1) +
            "\nv" +
            binding.source.version,
        },
      });
    }
    edges.push({
      id: "__binding-" + index,
      source: id,
      target: binding.target.node_id,
      label: binding.target.variable,
      className: issues.some(
        (issue) =>
          issue.node_id === binding.target.node_id &&
          (!issue.variable || issue.variable === binding.target.variable),
      )
        ? "graph-error"
        : "",
    });
  });
  const lastLevel = Math.max(1, ...levels.values()) + 1;
  workflow.output_definition.forEach((output, index) => {
    const id = "__output-" + index;
    nodes.push({
      id,
      type: "output",
      position: { x: lastLevel * 290, y: index * 120 },
      data: { label: "输出 · " + output.variable },
    });
    edges.push({ id: "__result-" + index, source: output.node_id, target: id });
  });
  return { nodes, edges };
}
