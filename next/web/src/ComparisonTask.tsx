import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, jobSchema } from "./api";
import { type TaskRecord } from "./draft";
import {
  useTaskDraft,
  saveMessage,
  type AdditionalSaveGuard,
} from "./useTaskDraft";
import { ConflictPanel } from "./ConflictPanel";
import { TaskRuns } from "./TaskRuns";
import { ErrorNotice, purposes } from "./shared";
const itemSchema = z.object({
  id: z.string(),
  task_id: z.string(),
  title: z.string(),
  purpose: z.enum(["assessment", "optimization", "temporal"]),
  draft_revision: z.number(),
  created: z.number(),
});
const listSchema = z.object({
  items: z.array(itemSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
const checkSchema = z.object({
  ready: z.boolean(),
  issues: z.array(z.object({ code: z.string(), message: z.string() })),
});
function SelectedResult({ id, label }: { id: string; label: string }) {
  const result = useQuery({
    queryKey: ["comparison-selection", id],
    queryFn: () =>
      api(
        `/jobs/${id}`,
        jobSchema.extend({
          manifest: z.object({
            draft: z.object({ title: z.string() }),
            draft_revision: z.number(),
          }),
        }),
      ),
  });
  return (
    <div>
      <strong>{label}：</strong>
      {result.data
        ? `${result.data.manifest.draft.title} · v${result.data.manifest.draft_revision}`
        : result.isPending
          ? "读取中…"
          : "不可读取"}
      <ErrorNotice error={result.error} />
    </div>
  );
}
export function ComparisonTask({
  initial,
  canEdit,
}: {
  initial: TaskRecord;
  canEdit: boolean;
}) {
  const cache = useQueryClient();
  const [noteGuard, setNoteGuard] = useState<AdditionalSaveGuard | null>(null);
  const onNoteGuard = useCallback(
    (guard: AdditionalSaveGuard | null) => setNoteGuard(guard),
    [],
  );
  const { session, snapshot, task } = useTaskDraft(initial, noteGuard);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<z.infer<typeof checkSchema>["issues"]>(
    [],
  );
  const listing = useQuery({
    queryKey: ["completed-results", task.project_id, page],
    queryFn: () =>
      api(
        `/projects/${task.project_id}/completed-results?limit=25&offset=${page * 25}`,
        listSchema,
      ),
  });
  const left =
    typeof task.draft.options.left_job_id === "string"
      ? task.draft.options.left_job_id
      : "";
  const right =
    typeof task.draft.options.right_job_id === "string"
      ? task.draft.options.right_job_id
      : "";
  async function run() {
    setBusy(true);
    setError(null);
    setIssues([]);
    try {
      await session.save();
      await noteGuard?.save();
      const check = await api(`/tasks/${task.id}/preflight`, checkSchema);
      setIssues(check.issues);
      if (!check.ready) return;
      await api(`/tasks/${task.id}/execute`, jobSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: session.snapshot().task.revision,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      await cache.invalidateQueries({ queryKey: ["jobs", task.id] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function select(side: "left_job_id" | "right_job_id", id: string) {
    setIssues([]);
    session.edit((d) => ({ ...d, options: { ...d.options, [side]: id } }));
  }
  return (
    <>
      <Link to={`/?project=${task.project_id}`}>← 科研任务</Link>
      <div className="section-heading">
        <h1>成果比较</h1>
        <p
          role="status"
          className={snapshot.status === "saved" ? "saved" : "warning"}
        >
          {saveMessage(snapshot.status)}
        </p>
      </div>
      <ErrorNotice error={error ?? snapshot.error} />
      <ConflictPanel session={session} onResolved={() => setError(null)} />
      {snapshot.status === "error" ? (
        <button
          type="button"
          className="secondary"
          onClick={() => void session.save().catch(setError)}
        >
          重试保存
        </button>
      ) : null}
      <fieldset className="task-controls" disabled={!canEdit || busy}>
        <label className="task-title">
          任务名称
          <input
            value={task.draft.title}
            onChange={(e) =>
              session.edit((d) => ({ ...d, title: e.target.value }))
            }
          />
        </label>
        <section>
          <h2>选择已有成果</h2>
          <p>选择同一项目内需要比较的运行。</p>
          <p>
            当前支持综合评价、空间优化及时间适配。其他模型成果的数值可比性尚未接入。
          </p>
          <div className="comparison-selection" aria-label="已选比较成果">
            {left ? (
              <SelectedResult id={left} label="基准成果" />
            ) : (
              <p>基准成果：尚未选择</p>
            )}
            {right ? (
              <SelectedResult id={right} label="对照成果" />
            ) : (
              <p>对照成果：尚未选择</p>
            )}
          </div>
          <ErrorNotice error={listing.error} />
          {listing.isPending ? (
            <p role="status">正在读取已完成成果…</p>
          ) : listing.data?.total === 0 ? (
            <p>暂无可比较成果。先完成评价、优化或时间适配任务，再返回选择。</p>
          ) : null}
          {listing.data && listing.data.total > 0 ? (
            <>
              <div className="table-scroll">
                <table aria-label="可比较成果">
                  <thead>
                    <tr>
                      <th>成果</th>
                      <th>方法类型</th>
                      <th>执行时间</th>
                      <th>基准</th>
                      <th>对照</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listing.data.items.map((item) => (
                      <tr key={item.id}>
                        <td>
                          {item.title} · v{item.draft_revision}
                        </td>
                        <td>{purposes[item.purpose]}</td>
                        <td>
                          {new Date(item.created * 1000).toLocaleString()}
                        </td>
                        <td>
                          <label className="comparison-choice">
                            <input
                              type="radio"
                              name="baseline"
                              aria-label={`作为基准：${item.title}，${new Date(item.created * 1000).toLocaleString()}`}
                              checked={left === item.id}
                              onChange={() => select("left_job_id", item.id)}
                            />
                          </label>
                        </td>
                        <td>
                          <label className="comparison-choice">
                            <input
                              type="radio"
                              name="contrast"
                              aria-label={`作为对照：${item.title}，${new Date(item.created * 1000).toLocaleString()}`}
                              checked={right === item.id}
                              onChange={() => select("right_job_id", item.id)}
                            />
                          </label>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="pagination">
                <span>
                  {page + 1} / {Math.ceil(listing.data.total / 25)} 页 · 共{" "}
                  {listing.data.total} 项
                </span>
                <button
                  type="button"
                  className="secondary"
                  disabled={!page}
                  onClick={() => setPage(page - 1)}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={(page + 1) * 25 >= listing.data.total}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </button>
              </div>
            </>
          ) : null}
        </section>
        <section>
          <h2>可比性核对与执行</h2>
          <p>
            同一资料和归一化基准的权重差异可作敏感性比较。跨来源、时期或方法尺度尚无依据时，保留原成果并说明阻断原因。
          </p>
          {issues.length ? (
            <ul role="alert">
              {issues.map((i) => (
                <li key={i.code}>{i.message}</li>
              ))}
            </ul>
          ) : null}
          <button
            type="button"
            disabled={!left || !right || left === right || busy}
            onClick={() => void run()}
          >
            核对并比较
          </button>
        </section>
      </fieldset>
      <TaskRuns
        onNoteGuard={onNoteGuard}
        beforeResultChange={noteGuard?.save}
        taskId={task.id}
        draftRevision={task.revision}
        canEdit={canEdit}
      />
    </>
  );
}
