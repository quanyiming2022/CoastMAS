import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, jobSchema } from "./api";
import { contract } from "./contracts";
import type {
  ResearchCaseSelection,
  VersionReference,
} from "./generated/contracts";
import { useWorkspace } from "./workspace";
import {
  Details,
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";
import ResearchReportView from "./ResearchReportView";

const reportSchema = z.object({
  kind: z.literal("research_evaluation"),
  report: contract("ResearchReport"),
  research_manifest: contract("ResearchManifest"),
  provider_requests: z.number().int().nonnegative(),
  input_fingerprint: z.string(),
});
type DraftCase = Omit<ResearchCaseSelection, "models"> & {
  models: VersionReference[];
};
const arms = ["A", "B", "C"] as const;
const armLabels = {
  A: "A · 规则规划",
  B: "B · LLM 推荐",
  C: "C · LLM + 知识图谱 + 约束",
};

export default function Research() {
  const { projectId } = useWorkspace();
  return <ResearchWorkspace key={projectId} projectId={projectId} />;
}
function ResearchWorkspace({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [sceneId, setSceneId] = useState("");
  const [goal, setGoal] = useState("可持续性评价：等权综合评价");
  const [modelIds, setModelIds] = useState<string[]>([]);
  const [assetIds, setAssetIds] = useState<string[]>([]);
  const [cases, setCases] = useState<DraftCase[]>([]);
  const [experiments, setExperiments] = useState<("A" | "B" | "C")[]>([
    ...arms,
  ]);
  const [repetitions, setRepetitions] = useState(1);
  const [allowProvider, setAllowProvider] = useState(false);
  const [page, setPage] = useState(0);
  const requestKey = useRef({ signature: "", key: "" });
  const catalog = useQuery({
    queryKey: ["research-catalog", projectId],
    queryFn: async ({ signal }) => {
      const [scenes, models, assets] = await Promise.all(
        ["scenes", "models", "data-assets"].map((path) =>
          request(
            `/${path}?project_id=${encodeURIComponent(projectId)}&limit=500`,
            z.array(resourceSchema),
            { signal },
          ),
        ),
      );
      return { scenes: scenes!, models: models!, assets: assets! };
    },
  });
  const jobs = useQuery({
    queryKey: ["research", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/research?project_id=${encodeURIComponent(projectId)}&limit=50&offset=${page * 50}`,
        z.array(jobSchema),
        { signal },
      ),
    refetchInterval: 5000,
  });
  const run = useMutation({
    mutationFn: () => {
      const body = {
        project_id: projectId,
        cases,
        experiments,
        repetitions,
        allow_provider: allowProvider,
      };
      const signature = JSON.stringify(body);
      if (requestKey.current.signature !== signature)
        requestKey.current = { signature, key: crypto.randomUUID() };
      return request("/research", jobSchema, {
        method: "POST",
        body,
        idempotencyKey: requestKey.current.key,
      });
    },
    onSuccess: (job) => navigate(`/research/${encodeURIComponent(job.id)}`),
  });
  function select(values: string[], id: string, checked: boolean) {
    return checked ? [...values, id] : values.filter((v) => v !== id);
  }
  function addCase() {
    const scene = catalog.data?.scenes.find((s) => s.id === sceneId);
    if (!scene || !catalog.data) return;
    const refs = (items: typeof catalog.data.models, ids: string[]) =>
      items
        .filter((i) => ids.includes(i.id))
        .map((i) => ({ id: i.id, version: i.version }));
    setCases((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        goal,
        scene: { id: scene.id, version: scene.version },
        models: refs(catalog.data.models, modelIds),
        assets: refs(catalog.data.assets, assetIds),
        selected_data: {},
      },
    ]);
  }
  const trials = cases.length * experiments.length * repetitions;
  return (
    <>
      <PageTitle
        title="科研验证"
        description="冻结场景与目录版本，对照规则、LLM 和知识图谱规划，保留失败与实际用量。"
      />
      {catalog.isPending ? <Loading /> : null}
      <ErrorNotice error={catalog.error ?? jobs.error ?? run.error} />
      <Panel title="建立固定研究样例">
        <label>
          研究场景
          <select value={sceneId} onChange={(e) => setSceneId(e.target.value)}>
            <option value="">选择场景</option>
            {catalog.data?.scenes.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · v{s.version}
              </option>
            ))}
          </select>
        </label>
        <label>
          研究目标
          <textarea
            value={goal}
            maxLength={8000}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <p>
          为所有实验选择相同的完整候选目录（最多12个模型、64份数据）。每类列出项目目录前500项；未选择的数据不会自动补入。
        </p>
        <fieldset>
          <legend>候选模型</legend>
          {catalog.data?.models.map((m) => (
            <label key={m.id}>
              <input
                type="checkbox"
                aria-label={`选择模型 ${m.id}`}
                disabled={!m.enabled}
                checked={modelIds.includes(m.id)}
                onChange={(e) =>
                  setModelIds(select(modelIds, m.id, e.target.checked))
                }
              />
              {m.name} · v{m.version}
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>候选数据</legend>
          {catalog.data?.assets.map((a) => (
            <label key={a.id}>
              <input
                type="checkbox"
                aria-label={`选择数据 ${a.id}`}
                disabled={!a.enabled}
                checked={assetIds.includes(a.id)}
                onChange={(e) =>
                  setAssetIds(select(assetIds, a.id, e.target.checked))
                }
              />
              {a.name} · v{a.version}
            </label>
          ))}
        </fieldset>
        <button
          disabled={
            !sceneId ||
            !goal.trim() ||
            !modelIds.length ||
            modelIds.length > 12 ||
            assetIds.length > 64 ||
            cases.length >= 20
          }
          onClick={addCase}
        >
          加入固定样例
        </button>
        <p>
          已选模型 {modelIds.length}/12，数据 {assetIds.length}/64；已加入{" "}
          {cases.length}/20 个样例。
        </p>
        {cases.map((c, index) => (
          <div className="toolbar" key={c.id}>
            <span>
              样例 {index + 1}：{c.goal} · {c.models.length}个模型 /{" "}
              {c.assets.length}份数据
            </span>
            <button
              className="secondary"
              onClick={() => setCases(cases.filter((item) => item.id !== c.id))}
            >
              移除样例 {index + 1}
            </button>
          </div>
        ))}
      </Panel>
      <Panel title="运行研究对照">
        {arms.map((a) => (
          <label key={a}>
            <input
              type="checkbox"
              checked={experiments.includes(a)}
              onChange={(e) =>
                setExperiments(
                  e.target.checked
                    ? [...experiments, a]
                    : experiments.filter((v) => v !== a),
                )
              }
            />
            {armLabels[a]}
          </label>
        ))}
        <label>
          重复次数
          <input
            type="number"
            min={1}
            max={5}
            value={repetitions}
            onChange={(e) => setRepetitions(Number(e.target.value))}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={allowProvider}
            onChange={(e) => setAllowProvider(e.target.checked)}
          />
          允许调用已配置的提供方
        </label>
        <p>
          未勾选或未配置时，B/C记录为阻塞；不退化成规则结果。只发送所选目录和场景摘要，不发送影像文件或存储地址。提供方来源与实际用量单独记录。
        </p>
        <p>
          本次 {trials}/100
          个试验；每个B/C试验最多1次提供方请求。这里评估规划候选，不执行候选模型。
        </p>
        <button
          disabled={
            run.isPending ||
            !cases.length ||
            !experiments.length ||
            trials > 100 ||
            !Number.isInteger(repetitions) ||
            repetitions < 1 ||
            repetitions > 5
          }
          onClick={() => run.mutate()}
        >
          提交科研评估
        </button>
      </Panel>
      <Panel title="科研任务记录">
        {jobs.data?.length ? (
          <table>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th>进度</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((j) => (
                <tr key={j.id}>
                  <td>
                    <Link to={`/research/${encodeURIComponent(j.id)}`}>
                      {j.id.slice(0, 12)}
                    </Link>
                  </td>
                  <td>
                    <Status value={j.status} />
                  </td>
                  <td>{Math.round(j.progress * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Empty>尚无科研任务。</Empty>
        )}
        <div className="pagination">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>
            上一页
          </button>
          <span>第{page + 1}页</span>
          <button
            disabled={!jobs.data || jobs.data.length < 50}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      </Panel>
    </>
  );
}
export function ResearchDetail() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  const client = useQueryClient();
  const job = useQuery({
    queryKey: ["research-job", projectId, id],
    queryFn: ({ signal }) =>
      request(`/jobs/${encodeURIComponent(id)}`, jobSchema, { signal }),
    refetchInterval: (q) =>
      q.state.data &&
      ["SUCCEEDED", "FAILED", "CANCELLED"].includes(q.state.data.status)
        ? false
        : 1500,
  });
  const report = useQuery({
    queryKey: ["research-report", projectId, id],
    queryFn: ({ signal }) =>
      request(`/research/${encodeURIComponent(id)}/report`, reportSchema, {
        signal,
      }),
    enabled: job.data?.status === "SUCCEEDED",
  });
  const cancel = useMutation({
    mutationFn: () =>
      request(`/jobs/${encodeURIComponent(id)}/cancel`, jobSchema, {
        method: "POST",
      }),
    onSuccess: (value) =>
      client.setQueryData(["research-job", projectId, id], value),
  });
  return (
    <>
      <Link to="/research">← 返回科研验证</Link>
      <PageTitle title="科研任务详情" description={id} />
      {job.isPending ? <Loading /> : null}
      <ErrorNotice error={job.error ?? report.error ?? cancel.error} />
      {job.data ? (
        <Panel title="报告生成状态">
          <Status value={job.data.status} />
          <progress aria-label="科研进度" value={job.data.progress} max={1} />
          <p>报告生成完成不代表所有试验有效；请检查下方评估状态与分母。</p>
          {["QUEUED", "RUNNING"].includes(job.data.status) ? (
            <button
              disabled={cancel.isPending || job.data.cancel_requested}
              onClick={() => cancel.mutate()}
            >
              {job.data.cancel_requested ? "等待取消确认" : "取消科研任务"}
            </button>
          ) : null}
          <Link to={`/runs/${encodeURIComponent(id)}`}>
            查看运行、取消与重试记录
          </Link>
          {job.data.error ? (
            <Details title="任务错误" value={job.data.error} />
          ) : null}
          <Details title="冻结研究输入" value={job.data.manifest} />
        </Panel>
      ) : null}
      {report.data ? (
        <>
          <a
            className="button"
            href={`/api/v1/research/${encodeURIComponent(id)}/report`}
            download={`research-${id}.json`}
          >
            下载完整科研报告
          </a>
          <ResearchReportView report={report.data.report} />
        </>
      ) : null}
    </>
  );
}
