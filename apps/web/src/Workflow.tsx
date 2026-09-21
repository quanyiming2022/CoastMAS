import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, revisionSchema, jobSchema } from "./api";
import { workflowContract } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  Details,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";
import WorkflowGraph from "./WorkflowGraph";
import type { WorkflowSpec } from "./generated/contracts";

const validationSchema = z.object({
  valid: z.boolean(),
  issues: z.array(
    z.object({
      code: z.string(),
      message: z.string(),
      node_id: z.string().nullable().optional(),
      variable: z.string().nullable().optional(),
    }),
  ),
  bindings: z.array(z.unknown()),
});
export default function Workflow() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  const query = useQuery({
    queryKey: ["workflow", projectId, id],
    queryFn: async ({ signal }) => {
      const revision = await request(
        "/workflows/" + encodeURIComponent(id),
        revisionSchema,
        { signal },
      );
      return workflowContract.parse(revision.spec);
    },
  });
  return (
    <>
      <Link to="/workflows">← 返回工作流</Link>
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      {query.data ? (
        <WorkflowWorkspace
          key={id + ":" + query.data.version}
          workflow={query.data}
        />
      ) : null}
    </>
  );
}
function WorkflowWorkspace({ workflow }: { workflow: WorkflowSpec }) {
  const { projectId } = useWorkspace();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [sceneId, setSceneId] = useState("");
  const [seed, setSeed] = useState(42);
  const scenes = useQuery({
    queryKey: ["scene-selection", projectId],
    queryFn: ({ signal }) =>
      request(
        "/scenes?project_id=" + encodeURIComponent(projectId) + "&limit=500",
        z.array(resourceSchema),
        { signal },
      ),
  });
  const scene = scenes.data?.find((item) => item.id === sceneId);
  const runKey = useRef({ selection: "", key: "" });
  const selection = {
    workflow_version: workflow.version,
    scene_id: sceneId,
    scene_version: scene?.version ?? 1,
    random_seed: seed,
  };
  const validate = useMutation({
    mutationFn: () =>
      request(
        `/workflows/${encodeURIComponent(workflow.id)}/validate`,
        validationSchema,
        { method: "POST", body: selection },
      ),
  });
  const run = useMutation({
    mutationFn: () => {
      const signature = JSON.stringify(selection);
      if (runKey.current.selection !== signature)
        runKey.current = { selection: signature, key: crypto.randomUUID() };
      return request(
        `/workflows/${encodeURIComponent(workflow.id)}/run`,
        jobSchema,
        { method: "POST", body: selection, idempotencyKey: runKey.current.key },
      );
    },
    onSuccess: (job) => {
      navigate("/runs/" + encodeURIComponent(job.id));
    },
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/workflows/${encodeURIComponent(workflow.id)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["workflows"] });
      navigate("/workflows");
    },
  });
  const busy = validate.isPending || run.isPending || archive.isPending;
  return (
    <>
      <PageTitle
        title={workflow.name}
        description={`版本 ${workflow.version} · ${workflow.nodes.length} 个计算节点 · ${workflow.input_bindings.length} 份数据绑定`}
      />
      <Link to={`/workflows/${encodeURIComponent(workflow.id)}/edit`}>
        编辑工作流 / 另存副本
      </Link>
      <button
        className="secondary"
        disabled={busy}
        onClick={() => archive.mutate()}
      >
        归档工作流
      </button>
      <ErrorNotice error={archive.error} />
      <Panel title="运行场景与科学预检">
        <div className="toolbar">
          <label>
            运行场景
            <select
              value={sceneId}
              disabled={busy}
              onChange={(event) => {
                setSceneId(event.target.value);
                validate.reset();
                run.reset();
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
            随机种子
            <input
              type="number"
              min={0}
              max={2147483647}
              value={seed}
              disabled={busy}
              onChange={(event) => {
                setSeed(Number(event.target.value));
                validate.reset();
              }}
            />
          </label>
          <button
            disabled={!scene || busy || !Number.isInteger(seed) || seed < 0}
            onClick={() => validate.mutate()}
          >
            {validate.isPending ? "校验中…" : "科学预检"}
          </button>
          <button
            disabled={!validate.data?.valid || busy}
            onClick={() => run.mutate()}
          >
            {run.isPending ? "提交中…" : "提交运行"}
          </button>
        </div>
        <ErrorNotice error={scenes.error ?? validate.error ?? run.error} />
        {validate.data ? (
          <>
            <Status value={validate.data.valid ? "VALIDATED" : "BLOCKED"} />
            {validate.data.issues.length ? (
              <ul>
                {validate.data.issues.map((issue, index) => (
                  <li key={index}>
                    <strong>
                      {issue.node_id ?? "工作流"} · {issue.code}
                    </strong>
                    ：{issue.message}
                  </li>
                ))}
              </ul>
            ) : (
              <p>本次预检通过。提交时服务端将再次检查版本、权限与科学约束。</p>
            )}
          </>
        ) : (
          <p className="muted">
            先选择场景并执行科学预检。修改场景或种子后必须重新校验。
          </p>
        )}
      </Panel>
      <Panel title="计算流程">
        <WorkflowGraph workflow={workflow} issues={validate.data?.issues} />
      </Panel>
      <Details title="精确版本、参数和数据绑定" value={workflow} />
    </>
  );
}
