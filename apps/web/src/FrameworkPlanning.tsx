import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, revisionSchema } from "./api";
import { planningContract, contract } from "./contracts";
import { ErrorNotice, Panel } from "./components";
import WorkflowGraph from "./WorkflowGraph";
const planContract = z.object({
  id: z.string(),
  artifact: planningContract,
  reserved_requests: z.literal(0),
});
export default function FrameworkPlanning({
  projectId,
  frameworkId,
  frameworkVersion,
  dataId,
  dataVersion,
}: {
  projectId: string;
  frameworkId: string;
  frameworkVersion: number;
  dataId: string;
  dataVersion: number;
}) {
  const navigate = useNavigate();
  const [sceneId, setSceneId] = useState("");
  const [method, setMethod] = useState("composite");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const scenes = useQuery({
    queryKey: ["framework-scenes", projectId],
    queryFn: ({ signal }) =>
      request(
        `/scenes?project_id=${encodeURIComponent(projectId)}&limit=500`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const selected = scenes.data?.find((item) => item.id === sceneId);
  const plan = useMutation({
    mutationFn: () =>
      request(
        `/indicator-frameworks/${encodeURIComponent(frameworkId)}/plan`,
        planContract,
        {
          method: "POST",
          body: {
            framework_version: frameworkVersion,
            data: { id: dataId, version: dataVersion },
            scene: { id: sceneId, version: selected!.version },
            assessment_method: method,
            idempotency_key: key,
          },
        },
      ),
  });
  const save = useMutation({
    mutationFn: () =>
      request(
        "/assessments",
        revisionSchema.extend({ spec: contract("AssessmentSpec") }),
        { method: "POST", body: { planning_trace_id: plan.data!.id } },
      ),
    onSuccess: (row) =>
      navigate(`/assessment-records/${encodeURIComponent(row.resource_id)}`),
  });
  const busy = plan.isPending || save.isPending;
  return (
    <Panel title="生成评价工作流">
      <ErrorNotice error={scenes.error ?? plan.error ?? save.error} />
      <p>
        权重方法由固定体系决定，多期数据自动加入变化与趋势节点；规划不调用外部模型。
      </p>
      <label>
        评价场景
        <select
          disabled={busy}
          value={sceneId}
          onChange={(event) => {
            setSceneId(event.target.value);
            setKey(crypto.randomUUID());
            plan.reset();
            save.reset();
          }}
        >
          <option value="">请选择场景</option>
          {scenes.data?.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} · v{item.version}
            </option>
          ))}
        </select>
      </label>
      <label>
        评价方法
        <select
          disabled={busy}
          value={method}
          onChange={(event) => {
            setMethod(event.target.value);
            setKey(crypto.randomUUID());
            plan.reset();
            save.reset();
          }}
        >
          <option value="composite">加权综合评价</option>
          <option value="topsis">TOPSIS（仅单期）</option>
        </select>
      </label>
      <button disabled={busy || !selected} onClick={() => plan.mutate()}>
        生成评价方案
      </button>
      {plan.data ? (
        <>
          <p>外部模型请求：{plan.data.reserved_requests}</p>
          {plan.data.artifact.missing_conditions.length ? (
            <ul role="alert">
              {plan.data.artifact.missing_conditions.map((issue, index) => (
                <li key={index}>
                  {issue.code}：{issue.message}
                </li>
              ))}
            </ul>
          ) : null}
          {plan.data.artifact.candidate_workflow ? (
            <>
              <WorkflowGraph workflow={plan.data.artifact.candidate_workflow} />
              <button disabled={busy} onClick={() => save.mutate()}>
                保存评价记录与工作流
              </button>
            </>
          ) : null}
        </>
      ) : null}
    </Panel>
  );
}
