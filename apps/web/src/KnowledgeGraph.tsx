import { DataTable } from "./components";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Position,
  MarkerType,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { request } from "./api";
import { contract } from "./contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle } from "./components";
import type {
  GraphNode,
  GraphEdge,
  GraphSnapshot,
} from "./generated/contracts";

const graphContract = contract("GraphSnapshot");
const nodeLabels: Record<GraphNode["type"], string> = {
  Objective: "目标",
  Task: "任务",
  Model: "模型",
  Variable: "变量",
  DataType: "数据类型",
  EntityType: "实体类型",
  SceneType: "场景类型",
  Constraint: "约束",
  DataAsset: "数据资产",
  Scene: "场景",
  Workflow: "工作流",
};
const relationLabels: Record<GraphEdge["type"], string> = {
  REQUIRES: "需要",
  PRODUCES: "产生",
  SUPPORTS: "支持",
  DEPENDS_ON: "依赖",
  MAPS_TO: "映射到",
  VALID_FOR: "适用于",
  INCOMPATIBLE_WITH: "不兼容",
  DERIVED_FROM: "来源于",
  CAN_FOLLOW: "候选下游",
};
const evidenceLabels: Record<GraphEdge["evidence"], string> = {
  declaration: "契约声明",
  workflow_declaration: "工作流声明",
  contract_candidate: "契约候选，仍需预检",
  contract_conflict: "契约冲突",
};
const resourcePaths: Partial<Record<GraphNode["type"], string>> = {
  Model: "models",
  DataAsset: "data",
  Scene: "scenes",
  Workflow: "workflows",
};

export default function KnowledgeGraph() {
  const { projectId } = useWorkspace();
  const [focus, setFocus] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);
  const [selected, setSelected] = useState("");
  const [relation, setRelation] = useState("");
  const [edgePage, setEdgePage] = useState(0);
  const all = useQuery({
    queryKey: ["knowledge-graph", projectId],
    queryFn: ({ signal }) =>
      request(
        `/knowledge-graph?project_id=${encodeURIComponent(projectId)}`,
        graphContract,
        { signal },
      ),
  });
  const effectiveFocus =
    focus ?? all.data?.nodes.find((node) => node.type === "Model")?.id ?? "";
  const neighborhood = useQuery({
    queryKey: ["knowledge-graph", projectId, effectiveFocus, depth],
    enabled: !!effectiveFocus,
    queryFn: ({ signal }) =>
      request(
        `/knowledge-graph?project_id=${encodeURIComponent(projectId)}&focus=${encodeURIComponent(effectiveFocus)}&depth=${depth}`,
        graphContract,
        { signal },
      ),
  });
  const current = effectiveFocus ? neighborhood : all;
  const nodeNames = useMemo(
    () => new Map(all.data?.nodes.map((node) => [node.id, node.label]) ?? []),
    [all.data],
  );
  const filteredEdges = useMemo(
    () =>
      current.data?.edges.filter(
        (edge) => !relation || edge.type === relation,
      ) ?? [],
    [current.data, relation],
  );
  const page = Math.min(
    edgePage,
    Math.max(0, Math.ceil(filteredEdges.length / 100) - 1),
  );
  const chosen = all.data?.nodes.find(
    (node) => node.id === (selected || effectiveFocus),
  );
  const selectedPath = chosen ? resourcePaths[chosen.type] : undefined;
  return (
    <>
      <PageTitle
        title="模型知识图谱"
        description="从当前项目的版本化契约浏览模型、输入数据、输出变量与下游关系。图谱关系不替代科学预检。"
      />
      <section className="panel">
        <div className="graph-toolbar">
          <label>
            中心节点
            <select
              aria-label="中心节点"
              value={effectiveFocus}
              onChange={(event) => {
                setFocus(event.target.value);
                setSelected("");
              }}
            >
              <option value="">完整图谱</option>
              {all.data?.nodes.map((node) => (
                <option key={node.id} value={node.id}>
                  {nodeLabels[node.type]} · {node.label}
                  {node.resource ? ` · v${node.resource.version}` : ""}
                </option>
              ))}
            </select>
          </label>
          <label>
            邻域深度
            <select
              aria-label="邻域深度"
              value={depth}
              onChange={(event) => setDepth(Number(event.target.value))}
            >
              {[0, 1, 2, 3, 4].map((value) => (
                <option key={value} value={value}>
                  {value} 层
                </option>
              ))}
            </select>
          </label>
          <label>
            关系类型
            <select
              aria-label="关系类型"
              value={relation}
              onChange={(event) => setRelation(event.target.value)}
            >
              <option value="">全部关系</option>
              {Object.entries(relationLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <ErrorNotice error={all.error ?? current.error} />
        {current.isPending ? (
          <Loading />
        ) : (
          current.data && (
            <GraphView
              snapshot={current.data}
              relation={relation}
              onSelect={setSelected}
              focus={effectiveFocus}
            />
          )
        )}
        <p className="muted">
          点击节点查看其来源；拖动画布、缩放或切换中心节点。候选下游仅表明变量契约相符，数据覆盖、CRS、基准及运行资格仍需预检。
        </p>
      </section>
      {chosen && (
        <section className="panel">
          <h2>节点详情：{chosen.label}</h2>
          <p>
            {nodeLabels[chosen.type]}
            {chosen.resource ? ` · 资源版本 ${chosen.resource.version}` : ""}
          </p>
          {chosen.resource && selectedPath && (
            <Link
              to={`/${selectedPath}/${encodeURIComponent(chosen.resource.id)}`}
            >
              打开来源资源
            </Link>
          )}
          <button
            className="secondary"
            onClick={() => {
              setFocus(chosen.id);
              setSelected("");
            }}
          >
            以此节点为中心
          </button>
          <dl>
            {Object.entries(chosen.properties ?? {}).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </dd>
              </div>
            ))}
          </dl>
          <details>
            <summary>稳定节点标识</summary>
            <code>{chosen.id}</code>
          </details>
        </section>
      )}
      {current.data && (
        <section className="panel">
          <h2>关系与证据</h2>

          <DataTable>
            <thead>
              <tr>
                <th>来源</th>
                <th>关系</th>
                <th>目标</th>
                <th>依据</th>
              </tr>
            </thead>
            <tbody>
              {filteredEdges.slice(page * 100, (page + 1) * 100).map((edge) => (
                <tr key={edge.id}>
                  <td>{nodeNames.get(edge.source)}</td>
                  <td>{relationLabels[edge.type]}</td>
                  <td>{nodeNames.get(edge.target)}</td>
                  <td>{evidenceLabels[edge.evidence]}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>

          {filteredEdges.length === 0 ? (
            <p className="empty">
              {current.data.edges.length
                ? "当前筛选无关系。"
                : "暂无关系记录。"}
            </p>
          ) : null}
          <div className="pagination">
            <button
              className="secondary"
              disabled={page === 0}
              onClick={() => setEdgePage(page - 1)}
            >
              上一页关系
            </button>
            <span>
              共 {filteredEdges.length} 条 · 第 {page + 1} 页
            </span>
            <button
              className="secondary"
              disabled={(page + 1) * 100 >= filteredEdges.length}
              onClick={() => setEdgePage(page + 1)}
            >
              下一页关系
            </button>
          </div>
        </section>
      )}
    </>
  );
}

function GraphView({
  snapshot,
  relation,
  onSelect,
  focus,
}: {
  snapshot: GraphSnapshot;
  relation: string;
  onSelect: (id: string) => void;
  focus: string;
}) {
  const graph = useMemo(() => {
    const selectedEdges = snapshot.edges.filter(
      (edge) => !relation || edge.type === relation,
    );
    const endpoints = new Set(
      selectedEdges.flatMap((edge) => [edge.source, edge.target]),
    );
    const selectedNodes = snapshot.nodes.filter(
      (node) => !relation || endpoints.has(node.id),
    );
    const columns: Record<GraphNode["type"], number> = {
      DataAsset: 0,
      Objective: 0,
      Scene: 0,
      Workflow: 0,
      Model: 1,
      Task: 1,
      Variable: 2,
      Constraint: 2,
      DataType: 3,
      EntityType: 3,
      SceneType: 3,
    };
    const rows = new Map<number, number>();
    const priorities: Partial<Record<GraphNode["type"], number>> = {
      Model: 0,
      DataAsset: 0,
      Variable: 0,
      Constraint: 2,
    };
    const arranged = [...selectedNodes].sort(
      (left, right) =>
        (priorities[left.type] ?? 1) - (priorities[right.type] ?? 1) ||
        left.label.localeCompare(right.label),
    );
    const nodes: Node[] = arranged.map((node) => {
      const column = columns[node.type],
        row = rows.get(column) ?? 0;
      rows.set(column, row + 1);
      return {
        id: node.id,
        position: { x: column * 310, y: row * 110 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: { label: `${nodeLabels[node.type]} · ${node.label}` },
        style: {
          width: 230,
          borderColor: node.type === "Model" ? "#07868b" : "#b2cccc",
        },
      };
    });
    const edges: Edge[] = selectedEdges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: relationLabels[edge.type],
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: edge.evidence === "contract_candidate" ? "#b4782e" : "#478c91",
        strokeDasharray:
          edge.evidence === "contract_candidate" ? "5 4" : undefined,
      },
    }));
    const adjacent = new Set(
      selectedEdges
        .filter((edge) => edge.source === focus || edge.target === focus)
        .flatMap((edge) => [edge.source, edge.target]),
    );
    const initialIds = new Set(
      selectedNodes
        .filter(
          (node) =>
            node.id === focus ||
            node.type === "DataAsset" ||
            (node.type === "Variable" && adjacent.has(node.id)),
        )
        .map((node) => node.id),
    );
    const initialNodes = focus
      ? nodes.filter((node) => initialIds.has(node.id))
      : nodes;
    return { nodes, edges, initialNodes };
  }, [snapshot, relation, focus]);
  if (graph.nodes.length > 300)
    return (
      <p role="status">
        当前视图有 {graph.nodes.length}{" "}
        个节点，请选择中心节点或减少邻域深度后查看交互图。下面仍列出查询关系。
      </p>
    );
  return (
    <div className="workflow-graph" aria-label="知识图谱交互画布">
      <ReactFlow
        key={snapshot.nodes.map((node) => node.id).join("|") + relation}
        nodes={graph.nodes}
        edges={graph.edges}
        fitView
        fitViewOptions={{
          nodes: graph.initialNodes,
          padding: 0.2,
          maxZoom: 0.85,
        }}
        minZoom={0.05}
        maxZoom={2}
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_, node) => onSelect(node.id)}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
