import { DataTable } from "./components";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema, jobSchema } from "./api";
import { contract, workflowContract, sceneContract } from "./contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle, Panel, Status } from "./components";
import WorkflowGraph from "./WorkflowGraph";
const recordContract = revisionSchema.extend({
  spec: contract("AssessmentSpec"),
});
const runsContract = z.array(
  z.object({ job: jobSchema, result_id: z.string().nullable() }),
);
const validationContract = z.object({
  valid: z.boolean(),
  issues: z.array(z.object({ code: z.string(), message: z.string() })),
});
export default function AssessmentRecords() {
  const { projectId } = useWorkspace();
  return <RecordList key={projectId} projectId={projectId} />;
}
function RecordList({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: ["assessment-records", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/assessments?${new URLSearchParams({ project_id: projectId, limit: "50", offset: String(page * 50) })}`,
        z.array(recordContract),
        { signal },
      ),
  });
  return (
    <>
      <Link to="/assessments">← 返回指标体系</Link>
      <PageTitle
        title="评价记录"
        description="固定指标体系、数据、场景与工作流配置，追踪匹配此配置的真实运行结果。"
      />
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <Panel title="已保存评价">
          <DataTable>
            <thead>
              <tr>
                <th>名称</th>
                <th className="numeric">版本</th>
                <th className="table-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.map((row) => (
                <tr key={row.resource_id}>
                  <td>{row.spec.name}</td>
                  <td className="numeric">v{row.version}</td>
                  <td className="table-actions">
                    <Link
                      to={`/assessment-records/${encodeURIComponent(row.resource_id)}`}
                    >
                      查看与运行
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          {!query.error && !query.data?.length ? (
            <p>从指标体系准备观测并保存评价方案，即可建立评价记录。</p>
          ) : null}
        </Panel>
      )}
      <div className="pagination">
        <button
          className="secondary"
          disabled={!page || query.isFetching}
          onClick={() => setPage(page - 1)}
        >
          上一页
        </button>
        <span>第 {page + 1} 页</span>
        <button
          className="secondary"
          disabled={query.data?.length !== 50 || query.isFetching}
          onClick={() => setPage(page + 1)}
        >
          下一页
        </button>
      </div>
    </>
  );
}
export function AssessmentRecord() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  return <Record key={`${projectId}:${id}`} id={id} projectId={projectId} />;
}
function Record({ id, projectId }: { id: string; projectId: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [seed, setSeed] = useState(42);
  const [runPage, setRunPage] = useState(0);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const query = useQuery({
    queryKey: ["assessment-record", projectId, id],
    queryFn: ({ signal }) =>
      request(`/assessments/${encodeURIComponent(id)}`, recordContract, {
        signal,
      }),
  });
  const spec = query.data?.spec;
  const workflow = useQuery({
    queryKey: [
      "assessment-workflow",
      projectId,
      spec?.workflow.id,
      spec?.workflow.version,
    ],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(
        `/workflows/${encodeURIComponent(spec!.workflow.id)}?version=${spec!.workflow.version}`,
        revisionSchema.extend({ spec: workflowContract }),
        { signal },
      ),
  });
  const scene = useQuery({
    queryKey: [
      "assessment-scene",
      projectId,
      spec?.scene.id,
      spec?.scene.version,
    ],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(
        `/scenes/${encodeURIComponent(spec!.scene.id)}?version=${spec!.scene.version}`,
        revisionSchema.extend({ spec: sceneContract }),
        { signal },
      ),
  });
  const runs = useQuery({
    queryKey: ["assessment-runs", projectId, id, spec?.version, runPage],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(
        `/assessments/${encodeURIComponent(id)}/runs?version=${spec!.version}&limit=50&offset=${runPage * 50}`,
        runsContract,
        { signal },
      ),
    refetchInterval: (query) =>
      query.state.data?.some((row) =>
        ["QUEUED", "RUNNING"].includes(row.job.status),
      )
        ? 2000
        : false,
  });
  const validate = useMutation({
    mutationFn: () =>
      request(
        `/workflows/${encodeURIComponent(spec!.workflow.id)}/validate`,
        validationContract,
        {
          method: "POST",
          body: {
            workflow_version: spec!.workflow.version,
            scene_id: spec!.scene.id,
            scene_version: spec!.scene.version,
            random_seed: seed,
          },
        },
      ),
  });
  const run = useMutation({
    mutationFn: () =>
      request(`/assessments/${encodeURIComponent(id)}/run`, jobSchema, {
        method: "POST",
        body: { assessment_version: spec!.version, random_seed: seed },
        idempotencyKey: key,
      }),
    onSuccess: (job) => navigate(`/runs/${encodeURIComponent(job.id)}`),
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/assessments/${encodeURIComponent(id)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["assessment-records"] });
      navigate("/assessment-records");
    },
  });
  const busy = validate.isPending || run.isPending || archive.isPending;
  if (query.isPending) return <Loading />;
  if (!spec) return <ErrorNotice error={query.error} />;
  return (
    <>
      <Link to="/assessment-records">← 返回评价记录</Link>
      <PageTitle
        title="评价记录详情"
        description={`${spec.name} · v${spec.version}`}
      />
      <ErrorNotice
        error={
          query.error ??
          workflow.error ??
          scene.error ??
          runs.error ??
          validate.error ??
          run.error ??
          archive.error
        }
      />
      <Panel title="固定评价配置">
        <p>
          <Link
            to={`/assessments/${encodeURIComponent(spec.framework.id)}?version=${spec.framework.version}`}
          >
            查看指标体系 v{spec.framework.version}
          </Link>
        </p>
        <p>
          <Link
            to={`/data/${encodeURIComponent(spec.data.id)}/workspace?version=${spec.data.version}`}
          >
            查看评价输入 v{spec.data.version}
          </Link>
        </p>
        <p>
          场景：{scene.data?.spec.name ?? spec.scene.id} · v{spec.scene.version}
        </p>
        <p>{scene.data?.spec.management_goal}</p>
        <p>
          工作流：{workflow.data?.spec.name ?? spec.workflow.id} · v
          {spec.workflow.version}
        </p>
        {workflow.data ? <WorkflowGraph workflow={workflow.data.spec} /> : null}
        <a
          href={`/api/v1/scenes/${encodeURIComponent(spec.scene.id)}?version=${spec.scene.version}`}
          download
        >
          下载固定场景定义
        </a>
      </Panel>
      <Panel title="运行评价">
        <label>
          随机种子
          <input
            disabled={busy}
            type="number"
            min={0}
            max={4294967295}
            value={Number.isFinite(seed) ? seed : ""}
            onChange={(event) => {
              setSeed(event.target.valueAsNumber);
              setKey(crypto.randomUUID());
              validate.reset();
              run.reset();
            }}
          />
        </label>
        <div className="toolbar">
          <button
            disabled={
              busy || !Number.isInteger(seed) || seed < 0 || seed > 4294967295
            }
            onClick={() => validate.mutate()}
          >
            科学预检
          </button>
          <button
            disabled={busy || !validate.data?.valid}
            onClick={() => run.mutate()}
          >
            提交评价运行
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => archive.mutate()}
          >
            归档评价记录
          </button>
        </div>
        {validate.data?.valid ? (
          <p>固定配置预检通过；提交时服务端会再次检查。</p>
        ) : null}
        {validate.data?.issues.length ? (
          <ul role="alert">
            {validate.data.issues.map((issue, index) => (
              <li key={index}>
                {issue.code}：{issue.message}
              </li>
            ))}
          </ul>
        ) : null}
        <p>
          归档只移出当前列表，保留固定配置与历史运行。修改评价条件须保存新的方案与记录。
        </p>
      </Panel>
      <Panel title="匹配固定配置的实际运行">
        <p>
          同时核对工作流、场景和输入版本，包含从工作流页面提交的同配置任务；不把任务成功自动解释为科学适用性审批。
        </p>
        <button disabled={runs.isFetching} onClick={() => void runs.refetch()}>
          刷新运行记录
        </button>
        <DataTable>
          <thead>
            <tr>
              <th>任务</th>
              <th>状态</th>
              <th>结果</th>
            </tr>
          </thead>
          <tbody>
            {runs.data?.map((row) => (
              <tr key={row.job.id}>
                <td>
                  <Link to={`/runs/${encodeURIComponent(row.job.id)}`}>
                    {row.job.id}
                  </Link>
                </td>
                <td>
                  <Status value={row.job.status} />
                </td>
                <td>
                  {row.result_id ? (
                    <Link to={`/results/${encodeURIComponent(row.result_id)}`}>
                      查看评价结果
                    </Link>
                  ) : (
                    "尚无已发布结果"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        {runs.isPending ? (
          <Loading />
        ) : !runs.error && !runs.data?.length ? (
          <p>此页暂无匹配运行。</p>
        ) : null}
        <div className="pagination">
          <button
            className="secondary"
            disabled={!runPage || runs.isFetching}
            onClick={() => setRunPage(runPage - 1)}
          >
            上一页运行
          </button>
          <span>第 {runPage + 1} 页</span>
          <button
            className="secondary"
            disabled={runs.data?.length !== 50 || runs.isFetching}
            onClick={() => setRunPage(runPage + 1)}
          >
            下一页运行
          </button>
        </div>
      </Panel>
    </>
  );
}
