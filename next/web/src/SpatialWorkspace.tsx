import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema, jobSchema } from "./api";
import { taskSchema, type TaskRecord } from "./draft";
import { AssetPicker } from "./AssetPicker";
import { CatalogUpload } from "./CatalogUpload";
import { AssetViewer } from "./AssetViewer";
import { initialDisplay, useViewState } from "./useViewState";
import { ResultArtifact } from "./ResultArtifact";
import { ErrorNotice } from "./shared";
const historySchema = z.object({
  items: z.array(jobSchema),
  total: z.number(),
});
export function SpatialWorkspace({
  task,
  canEdit,
}: {
  task: TaskRecord;
  canEdit: boolean;
}) {
  const [mobileTab, setMobileTab] = useState("map");
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [selected, setSelected] = useState<string | null>(null);
  const intent = useRef(crypto.randomUUID());
  const history = useQuery({
    queryKey: ["jobs", task.id],
    queryFn: () =>
      api(`/tasks/${task.id}/jobs?limit=25&offset=0`, historySchema),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => ["queued", "running"].includes(j.status))
        ? 700
        : false,
  });
  const job =
    history.data?.items.find((j) => j.id === selected) ??
    history.data?.items[0];
  const asset = useQuery({
    queryKey: ["asset", task.draft.selection[0]?.asset_id],
    enabled: !!task.draft.selection[0],
    queryFn: () =>
      api(`/assets/${task.draft.selection[0]!.asset_id}`, assetSchema),
  });
  const view = useViewState(`/tasks/${task.id}/view-state`);
  const state =
    view.active ?? initialDisplay(task.draft.selection[0]?.asset_id ?? "");
  async function selectSource(id: string) {
    setBusy(true);
    setError(null);
    try {
      const source = await api(`/assets/${id}`, assetSchema);
      if (!["geotiff", "cog"].includes(source.facts.profile))
        throw new Error("有效覆盖工具需要栅格；其他资料仍可在研究工作台查看。");
      const saved = await api(`/tasks/${task.id}/sources`, taskSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: task.revision,
          assets: [id],
        }),
      });
      cache.setQueryData(["task", task.id], saved);
      setMobileTab("map");
    } catch (e) {
      setError(e);
    } finally {
      await cache.invalidateQueries({ queryKey: ["task", task.id] });
      setBusy(false);
    }
  }
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const job = await api(`/tasks/${task.id}/execute`, jobSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: task.revision,
          idempotency_key: intent.current,
        }),
      });
      setSelected(job.id);
      await cache.invalidateQueries({ queryKey: ["jobs", task.id] });
      intent.current = crypto.randomUUID();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="catalog-workspace spatial-workspace">
      <div className="section-heading">
        <div>
          <h1>{task.draft.title}</h1>
          <p>草稿已保存 · 任务版本 {task.revision}</p>
        </div>
        <button
          type="button"
          disabled={
            !canEdit ||
            !task.draft.selection.length ||
            busy ||
            ["queued", "running"].includes(job?.status ?? "")
          }
          onClick={() => void run()}
        >
          预检并执行
        </button>
      </div>
      <ErrorNotice
        error={error ?? history.error ?? asset.error ?? view.error}
      />
      <div
        className="catalog-mobile-tabs"
        role="group"
        aria-label="空间工作区切换"
      >
        <button
          type="button"
          className={mobileTab === "map" ? "" : "secondary"}
          onClick={() => setMobileTab("map")}
        >
          当前主视图
        </button>
        <button
          type="button"
          className={mobileTab === "list" ? "" : "secondary"}
          onClick={() => setMobileTab("list")}
        >
          配置与运行
        </button>
      </div>
      <div className="catalog-layout" data-mobile-tab={mobileTab}>
        <section className="catalog-list" aria-label="空间处理配置">
          <h2>有效覆盖</h2>
          <p>
            按原始波段掩膜、NoData、有限值和透明通道计算。保留完整原生网格，输出
            1 为有效、0 为无效。
          </p>
          <p>零值及负数只要有效，就保留；不代表土地类别、海岸线或生态评价。</p>
          <dl>
            <dt>资料</dt>
            <dd>{asset.data?.name ?? "读取中"}</dd>
            <dt>波段</dt>
            <dd>{String(task.draft.options.band ?? 1)}</dd>
          </dl>
          <h3>运行记录</h3>
          <ul>
            {history.data?.items.map((j) => (
              <li key={j.id}>
                <button
                  type="button"
                  className="text-button"
                  aria-current={j.id === job?.id ? "true" : undefined}
                  onClick={() => setSelected(j.id)}
                >
                  {(
                    {
                      queued: "等待执行",
                      running: "实际计算中",
                      succeeded: "实际成果",
                      failed: "运行失败",
                      cancelled: "已取消",
                    } as Record<string, string>
                  )[j.status] ?? j.status}
                </button>
              </li>
            ))}
          </ul>
          {job && ["queued", "running"].includes(job.status) && canEdit ? (
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                try {
                  await api(`/jobs/${job.id}/cancel`, jobSchema, {
                    method: "POST",
                  });
                  await history.refetch();
                } catch (e) {
                  setError(e);
                }
              }}
            >
              取消运行
            </button>
          ) : null}
          {job?.status === "succeeded" ? (
            <a href={`/api/jobs/${job.id}/bundle`} download>
              下载完整成果包
            </a>
          ) : null}
        </section>
        <section className="catalog-detail" aria-label="空间处理工作区">
          {!task.draft.selection.length ? (
            <div className="source-choice">
              <h2>选择栅格资料</h2>
              <p>
                当前工具：生成有效覆盖。资料接入后自动显示，预检通过后再执行。
              </p>
              <CatalogUpload
                project={task.project_id}
                disabled={!canEdit || busy}
                onAsset={async (asset) => {
                  await selectSource(asset.id);
                }}
              />
              <AssetPicker
                project={task.project_id}
                selection={[]}
                disabled={!canEdit || busy}
                onSelect={selectSource}
              />
            </div>
          ) : job?.status === "succeeded" ? (
            <ResultArtifact key={job.id} jobId={job.id} />
          ) : (
            <>
              <p role="status">
                {job?.status === "running"
                  ? "正在计算完整原生网格；下方为输入资料"
                  : job?.status === "queued"
                    ? "等待执行；下方为输入资料"
                    : "输入资料 · 尚未生成本次成果"}
              </p>
              <ErrorNotice error={job?.error?.message} />
              {asset.data ? (
                <AssetViewer
                  asset={asset.data}
                  state={state}
                  onChange={(s) => void view.save(s).catch(() => {})}
                />
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
