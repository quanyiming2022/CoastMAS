import type {
  BindingTarget,
  ModelSpec,
  VersionReference,
  WorkflowEdge,
  WorkflowNode,
  WorkflowSpec,
} from "./generated/contracts";

export type WorkflowDraft = Omit<WorkflowSpec, "nodes"> & {
  nodes: WorkflowNode[];
};
export function emptyWorkflow(id: string): WorkflowDraft {
  return {
    id,
    name: "新工作流",
    version: 1,
    scene_type: "custom",
    nodes: [],
    edges: [],
    input_bindings: [],
    parameter_bindings: [],
    output_definition: [],
    constraints: [],
    validation_rules: [],
    execution_policy: { timeout_seconds: 300, max_retries: 0 },
  };
}
function requireNode(draft: WorkflowDraft, id: string) {
  if (!draft.nodes.some((node) => node.id === id))
    throw new Error("节点不存在");
}
export function addModel(
  draft: WorkflowDraft,
  model: Pick<ModelSpec, "id" | "version" | "parameters">,
  id: string,
): WorkflowDraft {
  if (!id.trim() || draft.nodes.some((node) => node.id === id))
    throw new Error("节点标识重复或为空");
  const parameters = Object.fromEntries(
    model.parameters
      .filter((parameter) => parameter.default != null)
      .map((parameter) => [parameter.name, parameter.default as number]),
  );
  return {
    ...draft,
    nodes: [
      ...draft.nodes,
      {
        id,
        model_id: model.id,
        model_version: model.version,
        kind: "model",
        parameters,
      },
    ],
  };
}
export function connectPorts(
  draft: WorkflowDraft,
  edge: WorkflowEdge,
): WorkflowDraft {
  requireNode(draft, edge.source_node);
  requireNode(draft, edge.target_node);
  if (!edge.source_variable.trim() || !edge.target_variable.trim())
    throw new Error("请选择输入和输出端口");
  if (
    draft.edges.some(
      (item) =>
        item.target_node === edge.target_node &&
        item.target_variable === edge.target_variable,
    ) ||
    draft.input_bindings.some(
      (item) =>
        item.target.node_id === edge.target_node &&
        item.target.variable === edge.target_variable,
    )
  )
    throw new Error("该输入已有来源，请先移除原绑定");
  const pending = [edge.target_node];
  const visited = new Set<string>();
  while (pending.length) {
    const current = pending.pop()!;
    if (current === edge.source_node)
      throw new Error("连线形成循环，工作流必须是有向无环图");
    if (visited.has(current)) continue;
    visited.add(current);
    pending.push(
      ...draft.edges
        .filter((item) => item.source_node === current)
        .map((item) => item.target_node),
    );
  }
  return { ...draft, edges: [...draft.edges, edge] };
}
export function assignData(
  draft: WorkflowDraft,
  target: BindingTarget,
  source: VersionReference | null,
): WorkflowDraft {
  requireNode(draft, target.node_id);
  if (
    source &&
    draft.edges.some(
      (edge) =>
        edge.target_node === target.node_id &&
        edge.target_variable === target.variable,
    )
  )
    throw new Error("请先删除该输入的连线");
  const bindings = draft.input_bindings.filter(
    (binding) =>
      binding.target.node_id !== target.node_id ||
      binding.target.variable !== target.variable,
  );
  if (source)
    bindings.push({
      target,
      source,
      status: "MANUAL_REVIEW",
      semantic_mapping: "exact_standard_name",
      unit_conversion: null,
      crs_transform: null,
      temporal_transform: null,
      resampling: null,
      quality_check: [],
    });
  return { ...draft, input_bindings: bindings };
}
export function setParameter(
  draft: WorkflowDraft,
  nodeId: string,
  name: string,
  value: number | undefined,
): WorkflowDraft {
  requireNode(draft, nodeId);
  if (value !== undefined && !Number.isFinite(value))
    throw new Error("参数必须是有限数值");
  return {
    ...draft,
    parameter_bindings: draft.parameter_bindings.filter(
      (binding) => binding.node_id !== nodeId || binding.parameter !== name,
    ),
    nodes: draft.nodes.map((node) => {
      if (node.id !== nodeId) return node;
      const parameters = { ...node.parameters };
      if (value === undefined) delete parameters[name];
      else parameters[name] = value;
      return { ...node, parameters };
    }),
  };
}
export function removeNode(draft: WorkflowDraft, id: string): WorkflowDraft {
  return {
    ...draft,
    nodes: draft.nodes.filter((node) => node.id !== id),
    edges: draft.edges.filter(
      (edge) => edge.source_node !== id && edge.target_node !== id,
    ),
    input_bindings: draft.input_bindings.filter(
      (binding) => binding.target.node_id !== id,
    ),
    parameter_bindings: draft.parameter_bindings.filter(
      (binding) => binding.node_id !== id,
    ),
    output_definition: draft.output_definition.filter(
      (output) => output.node_id !== id,
    ),
  };
}
