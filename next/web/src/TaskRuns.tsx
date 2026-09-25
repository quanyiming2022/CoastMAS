import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, jobSchema, resultSchema } from "./api";
import { ErrorNotice } from "./shared";
import { Collaboration } from "./Collaboration";
import { type AdditionalSaveGuard } from "./useTaskDraft";
import { ResultView } from "./ResultView";
const summarySchema = jobSchema.extend({
  created: z.number(),
  draft_revision: z.number(),
  cancel_requested: z.boolean(),
});
const historySchema = z.object({
  items: z.array(summarySchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});
const shortStatus: Record<string, string> = {
  queued: "等待",
  running: "计算中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};
const fullStatus: Record<string, string> = {
  queued: "等待执行",
  running: "计算中",
  succeeded: "工程执行成功",
  failed: "运行失败",
  cancelled: "运行已取消",
};
export function TaskRuns({
  taskId,
  draftRevision,
  canEdit,
  onNoteGuard,
  beforeResultChange,
}: {
  taskId: string;
  draftRevision: number;
  canEdit: boolean;
  onNoteGuard?: (guard: AdditionalSaveGuard | null) => void;
  beforeResultChange?: () => Promise<void>;
}) {
  const cache = useQueryClient();
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const history = useQuery({
    queryKey: ["jobs", taskId, page],
    queryFn: () =>
      api(`/tasks/${taskId}/jobs?limit=25&offset=${page * 25}`, historySchema),
    refetchInterval: (query) =>
      query.state.data?.items.some((job) =>
        ["queued", "running"].includes(job.status),
      )
        ? 700
        : false,
  });
  const current =
    history.data?.items.find((job) => job.id === selected) ??
    history.data?.items[0];
  const result = useQuery({
    queryKey: ["result", current?.id],
    enabled: current?.status === "succeeded",
    queryFn: () => api(`/jobs/${current!.id}/result`, resultSchema),
  });
  async function changeResult(nextPage: number, id: string | null) {
    try {
      await beforeResultChange?.();
      setPage(nextPage);
      setSelected(id);
    } catch (error) {
      setError(error);
    }
  }
  async function cancel() {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/jobs/${current.id}/cancel`, jobSchema, { method: "POST" });
      await cache.invalidateQueries({ queryKey: ["jobs", taskId] });
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="运行历史与成果">
      <h2>运行历史与成果</h2>
      <ErrorNotice error={history.error ?? error} />
      {history.isPending ? (
        <p role="status">正在读取运行历史…</p>
      ) : history.data?.total === 0 ? (
        <p>暂无运行记录。完成必要补充后可预检并执行。</p>
      ) : null}
      {history.data && history.data.total > 0 ? (
        <>
          <details className="disclosure">
            <summary>全部运行记录（{history.data.total} 次）</summary>
            <div className="table-scroll">
              <table aria-label="任务运行历史">
                <thead>
                  <tr>
                    <th>提交时间</th>
                    <th>任务版本</th>
                    <th>状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {history.data.items.map((job) => (
                    <tr key={job.id} aria-selected={current?.id === job.id}>
                      <td>{new Date(job.created * 1000).toLocaleString()}</td>
                      <td>v{job.draft_revision}</td>
                      <td>{shortStatus[job.status] ?? job.status}</td>
                      <td>
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => void changeResult(page, job.id)}
                          aria-label={`查看任务版本 ${job.draft_revision} 的运行（${new Date(job.created * 1000).toLocaleString()}）`}
                        >
                          {current?.id === job.id ? "正在查看" : "查看此运行"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination" aria-label="运行历史分页">
              <button
                type="button"
                className="secondary"
                disabled={page === 0}
                onClick={() => {
                  void changeResult(page - 1, null);
                }}
              >
                上一页
              </button>
              <span>
                第{page + 1}/{Math.max(1, Math.ceil(history.data.total / 25))}页
                · 共{history.data.total}次
              </span>
              <button
                type="button"
                className="secondary"
                disabled={(page + 1) * 25 >= history.data.total}
                onClick={() => {
                  void changeResult(page + 1, null);
                }}
              >
                下一页
              </button>
            </div>
          </details>
          {current ? (
            <>
              <p role="status" className="badge">
                {fullStatus[current.status] ?? current.status}
              </p>
              <p>
                本次运行固定任务 v{current.draft_revision}；当前草稿 v
                {draftRevision}。查看历史成果不会覆盖草稿或重新计算。
              </p>
              {canEdit && ["queued", "running"].includes(current.status) ? (
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || current.cancel_requested}
                  onClick={() => void cancel()}
                >
                  {current.cancel_requested
                    ? "已申请取消，等待执行确认"
                    : "取消此运行"}
                </button>
              ) : null}
              <ErrorNotice error={current.error?.message ?? result.error} />
              {result.isFetching && !result.data ? (
                <p role="status">正在读取成果…</p>
              ) : null}
              {result.data && current.status === "succeeded" ? (
                <>
                  <a
                    className="button"
                    href={`/api/jobs/${current.id}/download`}
                    download
                  >
                    下载运行记录
                  </a>
                  <p>运行记录包含本次配置、输入来源和验证状态。</p>
                  <ResultView
                    key={current.id}
                    jobId={current.id}
                    data={result.data.data}
                  />
                </>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
      {result.data?.data.scope === "immutable_result_comparison" && current ? (
        <Collaboration
          key={current.id}
          jobId={current.id}
          onGuardChange={onNoteGuard}
        />
      ) : null}
    </section>
  );
}
