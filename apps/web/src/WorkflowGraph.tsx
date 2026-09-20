import { useMemo } from "react";
import { ReactFlow, Background, Controls, MiniMap } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WorkflowSpec } from "./generated/contracts";
import { graphForWorkflow, type ValidationIssue } from "./workflow-graph";
const noIssues: ValidationIssue[] = [];
export default function WorkflowGraph({
  workflow,
  issues = noIssues,
}: {
  workflow: WorkflowSpec;
  issues?: ValidationIssue[];
}) {
  const graph = useMemo(
    () => graphForWorkflow(workflow, issues),
    [workflow, issues],
  );
  return (
    <div className="workflow-graph" aria-label="工作流节点与数据连接">
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        minZoom={0.15}
        maxZoom={2}
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>
    </div>
  );
}
