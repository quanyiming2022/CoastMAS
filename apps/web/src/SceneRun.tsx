import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, jobSchema } from "./api";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Panel, Status } from "./components";
import type { SceneSpec, VersionReference } from "./generated/contracts";
const preflightSchema = z.object({
  valid: z.boolean(),
  issues: z.array(z.object({ code: z.string(), message: z.string() })),
});

export default function SceneRun({ scene }: { scene: SceneSpec }) {
  const { projectId } = useWorkspace();
  const navigate = useNavigate();
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<VersionReference | null>(null);
  const catalog = useQuery({
    queryKey: ["scene-workflows", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/workflows?project_id=${encodeURIComponent(projectId)}&limit=50&offset=${page * 50}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const signature = JSON.stringify(selected);
  const submission = useRef({ signature: "", key: "" });
  const selection = {
    workflow_version: selected?.version,
    scene_id: scene.id,
    scene_version: scene.version,
    random_seed: 42,
  };
  const validate = useMutation({
    mutationFn: async () => ({
      signature,
      report: await request(
        `/workflows/${encodeURIComponent(selected!.id)}/validate`,
        preflightSchema,
        { method: "POST", body: selection },
      ),
    }),
  });
  const report =
    validate.data?.signature === signature ? validate.data.report : undefined;
  const run = useMutation({
    mutationFn: () => {
      if (submission.current.signature !== signature)
        submission.current = { signature, key: crypto.randomUUID() };
      return request(
        `/workflows/${encodeURIComponent(selected!.id)}/run`,
        jobSchema,
        {
          method: "POST",
          body: selection,
          idempotencyKey: submission.current.key,
        },
      );
    },
    onSuccess: (job) => navigate(`/runs/${encodeURIComponent(job.id)}`),
  });
  return (
    <Panel title={`运行场景 v${scene.version}`}>
      <ErrorNotice error={catalog.error ?? validate.error ?? run.error} />
      <label>
        执行工作流
        <select
          value={selected?.id ?? ""}
          disabled={run.isPending || validate.isPending}
          onChange={(event) => {
            const item = catalog.data?.find(
              (workflow) => workflow.id === event.target.value,
            );
            setSelected(item ? { id: item.id, version: item.version } : null);
          }}
        >
          <option value="">请选择工作流</option>
          {catalog.data
            ?.filter((item) => item.enabled)
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · v{item.version} · {item.id.slice(-8)}
              </option>
            ))}
        </select>
      </label>
      <div className="pagination">
        <button
          className="secondary"
          disabled={page === 0 || run.isPending || validate.isPending}
          onClick={() => {
            setPage((current) => current - 1);
            setSelected(null);
          }}
        >
          上一页工作流
        </button>
        <button
          className="secondary"
          disabled={
            (catalog.data?.length ?? 0) < 50 ||
            run.isPending ||
            validate.isPending
          }
          onClick={() => {
            setPage((current) => current + 1);
            setSelected(null);
          }}
        >
          下一页工作流
        </button>
        <button
          disabled={!selected || validate.isPending || run.isPending}
          onClick={() => validate.mutate()}
        >
          预检所选工作流
        </button>
        <button
          disabled={!report?.valid || validate.isPending || run.isPending}
          onClick={() => run.mutate()}
        >
          执行所选工作流
        </button>
      </div>
      {report ? (
        <>
          <Status value={report.valid ? "VALIDATED" : "BLOCKED"} />
          <ul>
            {report.issues.map((issue, index) => (
              <li key={index}>
                {issue.code}：{issue.message}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      <Link to="/results">查看项目结果</Link>
    </Panel>
  );
}
