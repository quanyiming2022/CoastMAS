import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, dashboardSchema } from "./api";
import { contract, planningContract } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  Details,
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
} from "./components";
import WorkflowGraph from "./WorkflowGraph";

const planSchema = z.object({
  id: z.string(),
  artifact: z
    .union([planningContract, contract("ProviderPlanningArtifact")])
    .nullable(),
  unresolved_goal: z.string().nullable(),
  reserved_requests: z.number().int().nonnegative(),
  max_provider_requests: z.number().int().positive(),
  allow_external: z.boolean(),
  usage_policy: z.string(),
});
type Plan = z.infer<typeof planSchema>;
const ledgerSchema = z.array(
  z.object({
    id: z.string(),
    ordinal: z.number().int(),
    status: z.string(),
    provider_model: z.string(),
    response_model: z.string().nullable(),
    usage: z.record(z.string(), z.unknown()).nullable(),
    error_code: z.string().nullable(),
    http_status: z.number().nullable(),
  }),
);
const presets = [
  "海岸影响筛查：海平面上升0.5米",
  "可持续性评价：等权综合评价",
  "多期变化评价：等权综合评价",
];

export default function Planner() {
  const { projectId } = useWorkspace();
  const navigate = useNavigate();
  const [goal, setGoal] = useState(presets[0] ?? "");
  const [sceneId, setSceneId] = useState("");
  const [allowExternal, setAllowExternal] = useState(false);
  const [selections, setSelections] = useState<Record<string, string>>({});
  const [plan, setPlan] = useState<Plan | null>(null);
  const [plannedSignature, setPlannedSignature] = useState("");
  const [latency, setLatency] = useState<number | null>(null);
  const requestKey = useRef({ signature: "", key: "" });
  const scenes = useQuery({
    queryKey: ["scene-selection", projectId],
    queryFn: ({ signal }) =>
      request(
        "/scenes?project_id=" + encodeURIComponent(projectId) + "&limit=500",
        z.array(resourceSchema),
        { signal },
      ),
  });
  const assets = useQuery({
    queryKey: ["planner-assets", projectId],
    queryFn: ({ signal }) =>
      request(
        "/data-assets?project_id=" +
          encodeURIComponent(projectId) +
          "&limit=500",
        z.array(resourceSchema),
        { signal },
      ),
  });
  const dashboard = useQuery({
    queryKey: ["dashboard", projectId],
    queryFn: ({ signal }) =>
      request(
        "/dashboard?project_id=" + encodeURIComponent(projectId),
        dashboardSchema,
        { signal },
      ),
  });
  const selectedScene = scenes.data?.find((scene) => scene.id === sceneId);
  const selectedData = Object.fromEntries(
    Object.entries(selections).flatMap(([target, id]) => {
      const asset = assets.data?.find((asset) => asset.id === id);
      return asset ? [[target, { id: asset.id, version: asset.version }]] : [];
    }),
  );
  const body = {
    project_id: projectId,
    scene: { id: sceneId, version: selectedScene?.version ?? 1 },
    goal,
    selected_data: selectedData,
    allow_external: allowExternal,
  };
  const signature = JSON.stringify(body);
  const stale = plan !== null && signature !== plannedSignature;
  const create = useMutation({
    mutationFn: async () => {
      if (requestKey.current.signature !== signature)
        requestKey.current = { signature, key: crypto.randomUUID() };
      const started = performance.now();
      const trace = await request("/plans", planSchema, {
        method: "POST",
        body,
        idempotencyKey: requestKey.current.key,
      });
      return {
        trace,
        signature,
        seconds: (performance.now() - started) / 1000,
      };
    },
    onSuccess: (result) => {
      setPlan(result.trace);
      setPlannedSignature(result.signature);
      setLatency(result.seconds);
    },
  });
  const resolve = useMutation({
    mutationFn: () =>
      request(
        `/plans/${encodeURIComponent(plan?.id ?? "")}/build-workflow`,
        planSchema,
        { method: "POST" },
      ),
    onSuccess: setPlan,
  });
  const save = useMutation({
    mutationFn: () =>
      request(
        `/plans/${encodeURIComponent(plan?.id ?? "")}/workflow`,
        z.object({
          id: z.string(),
          version: z.number().int(),
          planning_trace_id: z.string(),
        }),
        { method: "POST" },
      ),
    onSuccess: (workflow) =>
      navigate("/workflows/" + encodeURIComponent(workflow.id)),
  });
  const ledger = useQuery({
    queryKey: ["plan-ledger", projectId, plan?.id, plan?.reserved_requests],
    queryFn: ({ signal }) =>
      request(
        `/plans/${encodeURIComponent(plan?.id ?? "")}/requests`,
        ledgerSchema,
        { signal },
      ),
    enabled: plan !== null,
  });
  const busy = create.isPending || resolve.isPending || save.isPending;
  const artifact = plan?.artifact;
  const providerArtifact = artifact && "proposal" in artifact ? artifact : null;
  const deterministic = artifact && !("proposal" in artifact) ? artifact : null;
  const tasks =
    deterministic?.task_graph.nodes.map(
      (node) =>
        `${node.id} · ${node.model_id.split(":").at(-1)} v${node.model_version}`,
    ) ??
    providerArtifact?.proposal.task_graph ??
    [];
  const reasons =
    deterministic?.rationale ?? providerArtifact?.proposal.rationale ?? [];
  const missing =
    deterministic?.missing_conditions.map((item) => ({
      code: item.code,
      message: item.message,
    })) ??
    providerArtifact?.missing_conditions.map((message) => ({
      code: "PROVIDER_MISSING",
      message,
    })) ??
    [];
  return (
    <>
      <PageTitle
        title="智能编排"
        description="将管理目标拆解为受数据、版本和科学约束约束的候选流程。"
      />
      <ErrorNotice
        error={
          scenes.error ??
          assets.error ??
          dashboard.error ??
          create.error ??
          resolve.error ??
          save.error
        }
      />
      <div className="planner-grid">
        <Panel title="1 · 管理目标">
          <label>
            规划场景
            <select
              aria-label="规划场景"
              value={sceneId}
              disabled={busy}
              onChange={(event) => {
                setSceneId(event.target.value);
                setSelections({});
                setPlan(null);
              }}
            >
              <option value="">请选择场景</option>
              {scenes.data?.map((scene) => (
                <option key={scene.id} value={scene.id}>
                  {scene.name} · v{scene.version}
                </option>
              ))}
            </select>
          </label>
          <label className="spaced">
            管理目标
            <textarea
              aria-label="管理目标"
              rows={7}
              maxLength={8000}
              value={goal}
              disabled={busy}
              onChange={(event) => setGoal(event.target.value)}
            />
          </label>
          <details className="details">
            <summary>确定性模板示例</summary>
            <div className="preset-list">
              {presets.map((preset) => (
                <button
                  className="secondary"
                  key={preset}
                  disabled={busy}
                  onClick={() => {
                    setGoal(preset);
                    setSelections({});
                  }}
                >
                  {preset}
                </button>
              ))}
            </div>
          </details>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={allowExternal}
              disabled={busy || !dashboard.data?.provider_configured}
              onChange={(event) => setAllowExternal(event.target.checked)}
            />
            允许必要时请求外部模型
          </label>
          <p className="muted">
            规则可解决时不调用外部模型。外部请求最多两次，发送管理目标及授权目录摘要，不发送原始数据或凭证。
          </p>
          {dashboard.data && !dashboard.data.provider_configured ? (
            <p>外部模型未配置；确定性模板仍可使用。</p>
          ) : null}
          <button
            disabled={busy || !selectedScene || !goal.trim()}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "规划中…" : "生成规划"}
          </button>
        </Panel>
        <Panel title="2 · 任务拆解">
          {busy ? <Loading /> : null}
          {stale ? (
            <p role="status" className="error">
              输入已修改，请重新生成规划后再保存。
            </p>
          ) : null}
          {tasks.length ? (
            <ol className="value-list">
              {tasks.map((task, index) => (
                <li key={index}>{task}</li>
              ))}
            </ol>
          ) : (
            <Empty>提交目标后显示完整任务拆解。</Empty>
          )}
          {plan?.unresolved_goal ? (
            <div className="error">
              <p>目标超出当前确定性模板，原文已保留，没有忽略附加要求。</p>
              <p>{plan.unresolved_goal}</p>
              {plan.allow_external ? (
                <button
                  disabled={
                    busy ||
                    stale ||
                    plan.reserved_requests >= plan.max_provider_requests
                  }
                  onClick={() => resolve.mutate()}
                >
                  请求外部候选
                </button>
              ) : (
                <p>可调整为明确模板，或在配置外部模型后授权生成候选。</p>
              )}
            </div>
          ) : null}
          {providerArtifact ? (
            <p className="error">
              外部候选的目标解释需要人工复核。科学校验不证明任务解释完整正确。
            </p>
          ) : null}
          {latency !== null ? (
            <p className="muted">
              创建规划的客户端往返实测：{latency.toFixed(3)} 秒
            </p>
          ) : null}
        </Panel>
        <Panel title="3 · 数据与推荐依据">
          {missing.length ? (
            <ul className="value-list">
              {missing.map((item, index) => (
                <li key={index}>
                  <strong>{item.code}</strong>
                  <p>{item.message}</p>
                </li>
              ))}
            </ul>
          ) : artifact ? (
            <p>当前产物没有报告缺失条件。</p>
          ) : (
            <Empty>数据缺口、科学约束和推荐理由将在此显示。</Empty>
          )}
          {deterministic?.required_data.map((item) => {
            const key = item.target.node_id + "." + item.target.variable;
            return (
              <label className="spaced" key={key}>
                {key}
                <small>{item.standard_name}</small>
                <select
                  aria-label={key + " 的数据"}
                  disabled={busy}
                  value={selections[key] ?? item.selected?.id ?? ""}
                  onChange={(event) =>
                    setSelections((current) => ({
                      ...current,
                      [key]: event.target.value,
                    }))
                  }
                >
                  <option value="">自动匹配；多个合格候选将阻断</option>
                  {assets.data?.map((asset) => (
                    <option key={asset.id} value={asset.id}>
                      {asset.name} · v{asset.version}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
          <ul className="value-list">
            {reasons.map((reason, index) => (
              <li key={index}>{reason}</li>
            ))}
          </ul>
          <button
            disabled={busy || stale || !artifact?.candidate_workflow}
            onClick={() => save.mutate()}
          >
            保存工作流
          </button>
        </Panel>
      </div>
      {artifact?.candidate_workflow ? (
        <Panel title="候选流程 · 尚未执行">
          <WorkflowGraph workflow={artifact.candidate_workflow} />
        </Panel>
      ) : null}
      {plan ? (
        <Panel title="调用预算与真实账本">
          <p>
            已预留外部请求：{plan.reserved_requests} /{" "}
            {plan.max_provider_requests}
          </p>
          <p className="muted">
            预留不等于已完成的外部请求。Token
            用量仅显示提供方报告，未报告时保持未知。
          </p>
          <button className="secondary" onClick={() => void ledger.refetch()}>
            刷新调用账本
          </button>
          <ErrorNotice error={ledger.error} />
          {ledger.isPending ? <Loading /> : null}
          {ledger.data?.length === 0 ? <p>没有外部调用记录。</p> : null}
          {ledger.data?.map((item) => (
            <div className="ledger-entry" key={item.id}>
              <p>
                #{item.ordinal} · {item.status} · {item.provider_model}
              </p>
              <p>
                HTTP：{item.http_status ?? "未收到响应"}；错误：
                {item.error_code ?? "无已记录错误"}
              </p>
              <Details
                title={
                  item.usage === null ? "Token 用量未报告" : "提供方原始用量"
                }
                value={item.usage}
              />
            </div>
          ))}
          <Details title="规划产物与追踪标识" value={plan} />
        </Panel>
      ) : null}
    </>
  );
}
