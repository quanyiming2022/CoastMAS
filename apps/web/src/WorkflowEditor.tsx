import { useState } from "react";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ReactFlow,
  applyNodeChanges,
  applyEdgeChanges,
  type Edge,
  ReactFlowProvider,
  useReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type NodeProps,
  type XYPosition,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { z } from "zod";
import { request, resourceSchema, revisionSchema } from "./api";
import { modelContract, workflowContract } from "./contracts";
import { ErrorNotice, Loading, PageTitle, Panel, Status } from "./components";
import { useWorkspace } from "./workspace";
import type { ModelSpec, WorkflowSpec } from "./generated/contracts";
import {
  addModel,
  assignData,
  connectPorts,
  emptyWorkflow,
  removeNode,
  setParameter,
  type WorkflowDraft,
} from "./workflow-editor";

const preflightSchema = z.object({
  valid: z.boolean(),
  issues: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      node_id: z.string().nullable().optional(),
    }),
  ),
});
type ModelNode = Node<
  {
    model?: ModelSpec;
    modelId: string;
    version: number;
    errors: string[];
    checked: boolean;
  },
  "model"
>;
function ModelCard({ data }: NodeProps<ModelNode>) {
  return (
    <div className={`editor-node ${data.errors.length ? "graph-error" : ""}`}>
      <strong>{data.model?.name ?? data.modelId}</strong>
      <small>
        v{data.version} ·{" "}
        {data.errors.length ? "存在错误" : data.checked ? "已验证" : "待预检"}
      </small>
      {data.model?.inputs.map((input) => (
        <div className="editor-port" key={"in:" + input.name}>
          <Handle
            type="target"
            position={Position.Left}
            id={"in:" + input.name}
          />
          <span>
            输入 · {input.name} [{input.unit}]
          </span>
        </div>
      ))}
      {data.model?.outputs.map((output) => (
        <div className="editor-port" key={"out:" + output.name}>
          <span>
            输出 · {output.name} [{output.unit}]
          </span>
          <Handle
            type="source"
            position={Position.Right}
            id={"out:" + output.name}
          />
        </div>
      ))}
      {data.errors.map((error) => (
        <small key={error}>{error}</small>
      ))}
    </div>
  );
}
const nodeTypes = { model: ModelCard };
export default function WorkflowEditor() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  const existing = useQuery({
    queryKey: ["workflow", projectId, id],
    enabled: !!id,
    queryFn: async ({ signal }) =>
      workflowContract.parse(
        (
          await request(
            `/workflows/${encodeURIComponent(id!)}`,
            revisionSchema,
            { signal },
          )
        ).spec,
      ),
  });
  if (id && existing.isPending) return <Loading />;
  if (existing.error) return <ErrorNotice error={existing.error} />;
  return (
    <ReactFlowProvider key={id ?? "new"}>
      <Editor initial={existing.data} />
    </ReactFlowProvider>
  );
}
function Editor({ initial }: { initial?: WorkflowSpec }) {
  const { projectId } = useWorkspace();
  const client = useQueryClient();
  const navigate = useNavigate();
  const { screenToFlowPosition } = useReactFlow();
  const [draft, setDraft] = useState<WorkflowDraft>(
    () => initial ?? emptyWorkflow(`workflow-${crypto.randomUUID()}`),
  );
  const [positions, setPositions] = useState<Record<string, XYPosition>>({});
  const [selected, setSelected] = useState("");
  const [nodeViews, setNodeViews] = useState<ModelNode[]>([]);
  const [edgeViews, setEdgeViews] = useState<Edge[]>([]);
  const [error, setError] = useState<Error | null>(null);
  const [sceneId, setSceneId] = useState("");
  const catalogs = useQueries({
    queries: ["models", "data-assets", "scenes"].map((kind) => ({
      queryKey: ["editor-catalog", projectId, kind],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        request(
          `/${kind}?project_id=${encodeURIComponent(projectId)}&limit=500`,
          z.array(resourceSchema),
          { signal },
        ),
    })),
  });
  const modelList = catalogs[0]?.data ?? [];
  const assets = catalogs[1]?.data ?? [];
  const scenes = catalogs[2]?.data ?? [];
  const modelRefs = [
    ...new Map(
      draft.nodes.map((node) => [
        node.model_id + "@" + node.model_version,
        { id: node.model_id, version: node.model_version },
      ]),
    ).values(),
  ];
  const models = useQueries({
    queries: modelRefs.map((reference) => ({
      queryKey: ["editor-model", reference.id, reference.version],
      queryFn: async ({ signal }: { signal: AbortSignal }) =>
        modelContract.parse(
          (
            await request(
              `/models/${encodeURIComponent(reference.id)}?version=${reference.version}`,
              revisionSchema,
              { signal },
            )
          ).spec,
        ),
    })),
  });
  const modelFor = (id: string, version: number) =>
    models.find(
      (query) => query.data?.id === id && query.data.version === version,
    )?.data;
  const scene = scenes.find((item) => item.id === sceneId);
  const signature = JSON.stringify({
    draft,
    sceneId,
    sceneVersion: scene?.version,
  });
  const validate = useMutation({
    mutationFn: async () => ({
      signature,
      report: await request("/workflow-drafts/validate", preflightSchema, {
        method: "POST",
        body: {
          project_id: projectId,
          workflow: workflowContract.parse(draft),
          scene: { id: sceneId, version: scene?.version },
          random_seed: 42,
        },
      }),
    }),
  });
  const report =
    validate.data?.signature === signature ? validate.data.report : undefined;
  const save = useMutation({
    mutationFn: async (copy: boolean) => {
      const spec = workflowContract.parse({
        ...draft,
        id: copy ? `workflow-${crypto.randomUUID()}` : draft.id,
        name: copy ? draft.name + " 副本" : draft.name,
        version: copy ? 1 : (initial?.version ?? 0) + 1,
      });
      const result = await request(
        initial && !copy
          ? `/workflows/${encodeURIComponent(initial.id)}`
          : "/workflows",
        revisionSchema,
        {
          method: initial && !copy ? "PUT" : "POST",
          body:
            initial && !copy
              ? { expected_version: initial.version, spec }
              : { project_id: projectId, spec },
        },
      );
      return workflowContract.parse(result.spec);
    },
    onSuccess: async (spec) => {
      client.setQueryData(["workflow", projectId, spec.id], spec);
      navigate(`/workflows/${encodeURIComponent(spec.id)}`);
      await client.invalidateQueries({ queryKey: ["workflows", projectId] });
    },
  });
  function change(update: (current: WorkflowDraft) => WorkflowDraft) {
    try {
      const next = update(draft);
      setDraft(next);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    }
  }
  const adding = useMutation({
    mutationFn: async ({
      id,
      position,
    }: {
      id: string;
      position?: XYPosition;
    }) => {
      const reference = modelList.find((item) => item.id === id);
      if (!reference) throw new Error("模型不在当前项目目录中");
      const model = await client.fetchQuery({
        queryKey: ["editor-model", id, reference.version],
        queryFn: async () =>
          modelContract.parse(
            (
              await request(
                `/models/${encodeURIComponent(id)}?version=${reference.version}`,
                revisionSchema,
              )
            ).spec,
          ),
      });
      return { model, position, nodeId: `node-${crypto.randomUUID()}` };
    },
    onSuccess: ({ model, position, nodeId }) => {
      setDraft((current) => addModel(current, model, nodeId));
      const nextPosition = position ?? {
        x: draft.nodes.length
          ? Math.max(
              ...draft.nodes.map(
                (item, index) =>
                  (nodeViews.find((view) => view.id === item.id)?.position.x ??
                    positions[item.id]?.x ??
                    (index % 3) * 360) +
                  (nodeViews.find((view) => view.id === item.id)?.measured
                    ?.width ?? 280),
              ),
            ) + 80
          : 0,
        y: 0,
      };
      setPositions((current) => ({ ...current, [nodeId]: nextPosition }));
      setNodeViews((current) =>
        current.map((view) => ({ ...view, selected: false })),
      );
      setSelected(nodeId);
    },
  });
  const node = draft.nodes.find((item) => item.id === selected);
  const model = node && modelFor(node.model_id, node.model_version);
  const busy = save.isPending || adding.isPending;
  const viewNodes: ModelNode[] = draft.nodes.map((item, index) => ({
    id: item.id,
    type: "model",
    position: nodeViews.find((view) => view.id === item.id)?.position ??
      positions[item.id] ?? {
        x: (index % 3) * 360,
        y: Math.floor(index / 3) * 320,
      },
    measured: nodeViews.find((view) => view.id === item.id)?.measured,
    selected:
      nodeViews.find((view) => view.id === item.id)?.selected ??
      selected === item.id,
    data: {
      model: modelFor(item.model_id, item.model_version),
      modelId: item.model_id,
      version: item.model_version,
      checked: !!report?.valid,
      errors:
        report?.issues
          .filter((issue) => issue.node_id === item.id)
          .map((issue) => issue.code) ?? [],
    },
  }));
  const viewEdges: Edge[] = draft.edges.map((edge) => {
    const id = JSON.stringify(edge);
    return {
      id,
      source: edge.source_node,
      target: edge.target_node,
      sourceHandle: "out:" + edge.source_variable,
      targetHandle: "in:" + edge.target_variable,
      label: edge.source_variable + " → " + edge.target_variable,
      selected: edgeViews.find((view) => view.id === id)?.selected ?? false,
    };
  });

  return (
    <>
      <Link to="/workflows">← 返回工作流</Link>
      <PageTitle
        title="工作流编辑器"
        description="拖入模型并连接明确的输入、输出端口。所有科学约束由真实预检和运行关卡执行。"
      />
      <ErrorNotice
        error={
          error ??
          save.error ??
          adding.error ??
          validate.error ??
          catalogs.find((query) => query.error)?.error ??
          models.find((query) => query.error)?.error
        }
      />
      <div className="toolbar">
        <label>
          工作流名称
          <input
            value={draft.name}
            disabled={busy}
            onChange={(event) =>
              change((current) => ({ ...current, name: event.target.value }))
            }
          />
        </label>
        <label>
          场景类型
          <input
            value={draft.scene_type}
            disabled={busy}
            onChange={(event) =>
              change((current) => ({
                ...current,
                scene_type: event.target.value,
              }))
            }
          />
        </label>
        <button
          disabled={busy || !draft.nodes.length}
          onClick={() => save.mutate(false)}
        >
          {save.isPending ? "保存中…" : "保存工作流版本"}
        </button>
        <button
          className="secondary"
          disabled={busy || !draft.nodes.length}
          onClick={() => save.mutate(true)}
        >
          另存副本
        </button>
        {initial ? (
          <span>基于 v{initial.version} 修订；保存后可运行</span>
        ) : null}
      </div>
      <div className="editor-layout">
        <Panel title="模型工具箱">
          <p className="muted">拖到画布，或点击添加。</p>
          {catalogs[0]?.isPending ? <Loading /> : null}
          <div className="editor-palette">
            {modelList
              .filter((item) => item.enabled)
              .map((item) => (
                <button
                  key={item.id}
                  className="secondary"
                  disabled={busy}
                  draggable={!busy}
                  onDragStart={(event) =>
                    event.dataTransfer.setData(
                      "application/coastmas-model",
                      item.id,
                    )
                  }
                  onClick={() => adding.mutate({ id: item.id })}
                >
                  {item.name} · v{item.version}
                </button>
              ))}
          </div>
          {modelList.length === 500 ? (
            <p role="alert">
              目录达到 500
              条上限，请精简项目目录后继续；未加载项不会隐式参与编辑。
            </p>
          ) : null}
        </Panel>
        <div
          className="workflow-graph editor-canvas"
          aria-label="工作流编辑画布"
          onDragOver={(event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
          }}
          onDrop={(event) => {
            event.preventDefault();
            const id = event.dataTransfer.getData("application/coastmas-model");
            if (id && !busy)
              adding.mutate({
                id,
                position: screenToFlowPosition({
                  x: event.clientX,
                  y: event.clientY,
                }),
              });
          }}
        >
          <ReactFlow<ModelNode>
            nodeTypes={nodeTypes}
            nodes={viewNodes}
            edges={viewEdges}
            onNodeClick={(_, item) => setSelected(item.id)}
            onNodesChange={(changes) =>
              setNodeViews(applyNodeChanges(changes, viewNodes))
            }
            onEdgesChange={(changes) =>
              setEdgeViews(applyEdgeChanges(changes, viewEdges))
            }
            onConnect={(connection) =>
              change((current) =>
                connectPorts(current, {
                  source_node: connection.source,
                  source_variable: connection.sourceHandle?.slice(4) ?? "",
                  target_node: connection.target,
                  target_variable: connection.targetHandle?.slice(3) ?? "",
                }),
              )
            }
            onEdgesDelete={(removed) =>
              change((current) => ({
                ...current,
                edges: current.edges.filter(
                  (candidate) =>
                    !removed.some(
                      (edge) => edge.id === JSON.stringify(candidate),
                    ),
                ),
              }))
            }
            onNodesDelete={(removed) =>
              change((current) =>
                removed.reduce(
                  (next, item) => removeNode(next, item.id),
                  current,
                ),
              )
            }
            nodesDraggable={!busy}
            nodesConnectable={!busy}
            deleteKeyCode={busy ? null : ["Backspace", "Delete"]}
            minZoom={0.15}
            maxZoom={2}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      </div>
      <Panel title="节点参数、数据与输出">
        <label>
          选择节点
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">请选择节点</option>
            {draft.nodes.map((item) => (
              <option key={item.id} value={item.id}>
                {modelFor(item.model_id, item.model_version)?.name ??
                  item.model_id}{" "}
                · {item.id.slice(-8)}
              </option>
            ))}
          </select>
        </label>
        {node && model ? (
          <fieldset disabled={busy}>
            <legend>
              {model.name} · v{model.version}
            </legend>
            <button
              className="secondary"
              onClick={() => change((current) => removeNode(current, node.id))}
            >
              删除选中节点
            </button>
            <div className="toolbar">
              {model.parameters.map((parameter) => (
                <label key={parameter.name}>
                  {parameter.name} [{parameter.unit}]
                  {parameter.required ? "（必填）" : ""}
                  <input
                    type="number"
                    step="any"
                    min={parameter.minimum ?? undefined}
                    max={parameter.maximum ?? undefined}
                    value={
                      node.parameters?.[parameter.name] ??
                      draft.parameter_bindings.find(
                        (binding) =>
                          binding.node_id === node.id &&
                          binding.parameter === parameter.name,
                      )?.value ??
                      ""
                    }
                    onChange={(event) =>
                      change((current) =>
                        setParameter(
                          current,
                          node.id,
                          parameter.name,
                          event.target.value === ""
                            ? undefined
                            : Number(event.target.value),
                        ),
                      )
                    }
                  />
                </label>
              ))}
            </div>
            {model.inputs.map((input) => {
              const binding = draft.input_bindings.find(
                (item) =>
                  item.target.node_id === node.id &&
                  item.target.variable === input.name,
              );
              const edge = draft.edges.find(
                (item) =>
                  item.target_node === node.id &&
                  item.target_variable === input.name,
              );
              const chosen = binding
                ? `${binding.source.id}@${binding.source.version}`
                : "";
              return (
                <label key={input.name}>
                  输入数据 · {input.name} [{input.unit}]
                  <select
                    disabled={!!edge || busy}
                    value={chosen}
                    onChange={(event) => {
                      const asset = assets.find(
                        (item) =>
                          `${item.id}@${item.version}` === event.target.value,
                      );
                      change((current) =>
                        assignData(
                          current,
                          { node_id: node.id, variable: input.name },
                          asset
                            ? { id: asset.id, version: asset.version }
                            : null,
                        ),
                      );
                    }}
                  >
                    <option value="">
                      {edge ? "已连接上游节点" : "未绑定"}
                    </option>
                    {binding &&
                    !assets.some(
                      (item) => `${item.id}@${item.version}` === chosen,
                    ) ? (
                      <option value={chosen}>
                        {binding.source.id} · v{binding.source.version}
                        （固定历史版本）
                      </option>
                    ) : null}
                    {assets
                      .filter((item) => item.enabled)
                      .map((item) => (
                        <option
                          key={item.id}
                          value={`${item.id}@${item.version}`}
                        >
                          {item.name} · v{item.version}
                        </option>
                      ))}
                  </select>
                </label>
              );
            })}
            {model.outputs.map((output) => (
              <label className="checkbox-label" key={output.name}>
                <input
                  type="checkbox"
                  checked={draft.output_definition.some(
                    (item) =>
                      item.node_id === node.id && item.variable === output.name,
                  )}
                  onChange={(event) =>
                    change((current) => ({
                      ...current,
                      output_definition: event.target.checked
                        ? [
                            ...current.output_definition,
                            { node_id: node.id, variable: output.name },
                          ]
                        : current.output_definition.filter(
                            (item) =>
                              item.node_id !== node.id ||
                              item.variable !== output.name,
                          ),
                    }))
                  }
                />
                发布输出 · {output.name} [{output.unit}]
              </label>
            ))}
          </fieldset>
        ) : (
          <p>选择一个节点以编辑参数和数据绑定。</p>
        )}
        <ul>
          {draft.edges.map((edge, index) => (
            <li key={index}>
              {edge.source_variable} → {edge.target_variable}
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  change((current) => ({
                    ...current,
                    edges: current.edges.filter(
                      (_, position) => position !== index,
                    ),
                  }))
                }
              >
                删除连线 {index + 1}
              </button>
            </li>
          ))}
        </ul>
      </Panel>
      <Panel title="草稿科学预检">
        <div className="toolbar">
          <label>
            预检场景
            <select
              value={sceneId}
              onChange={(event) => setSceneId(event.target.value)}
            >
              <option value="">请选择场景</option>
              {scenes
                .filter((item) => item.enabled)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · v{item.version}
                  </option>
                ))}
            </select>
          </label>
          <button
            disabled={
              !scene || !draft.nodes.length || validate.isPending || busy
            }
            onClick={() => validate.mutate()}
          >
            校验当前草稿
          </button>
        </div>
        {report ? (
          <>
            <Status value={report.valid ? "VALIDATED" : "BLOCKED"} />
            <ul>
              {report.issues.map((issue, index) => (
                <li key={index}>
                  {issue.node_id ?? "工作流"} · {issue.code}：{issue.message}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="muted">
            修改草稿后需重新预检。保存不会绕过运行时的科学与权限检查。
          </p>
        )}
      </Panel>
    </>
  );
}
