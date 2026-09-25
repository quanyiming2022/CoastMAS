import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError, type Asset } from "./api";
import { SourceSnapshotPicker } from "./SourceSnapshotPicker";
import { CatalogUpload } from "./CatalogUpload";
import { ErrorNotice } from "./shared";
import { taskSchema, type TaskRecord } from "./draft";
const itemSchema = z.object({
  id: z.string(),
  status: z.string(),
  asset_id: z.string().nullable(),
  source: z.object({
    name: z.string(),
    size: z.number(),
    source_id: z.string().nullable(),
    path: z.string().nullable(),
  }),
  error: z.object({ code: z.string(), message: z.string() }).nullable(),
});
const batchSchema = z.object({ id: z.string(), items: z.array(itemSchema) });
const labels: Record<string, string> = {
  queued: "等待服务器接入",
  receiving: "正在读取",
  awaiting_upload: "等待上传，可重新选择原文件",
  failed: "失败，可单项重试",
  ready: "已接入并绑定任务",
};
export function ImportPanel({
  task,
  beforeImport,
  onSynced,
  onPreview,
  onBusy,
  mode,
}: {
  task: TaskRecord;
  mode?: "upload" | "source";
  beforeImport: () => Promise<void>;
  onSynced: (task: TaskRecord) => void;
  onPreview?: (assetId: string, taskId: string) => Promise<void>;
  onBusy: (busy: boolean) => void;
}) {
  const cache = useQueryClient(),
    lastSignature = useRef("");
  const targetId = useRef<string | null>(null);
  const previewed = useRef(false);
  const targetSchema = z.object({
    id: z.string(),
    entries: z.array(
      z.object({
        asset_id: z.string().nullable(),
        name: z.string().nullable(),
        status: z.string(),
        error: z.object({ code: z.string(), message: z.string() }).nullable(),
      }),
    ),
  });
  const recovery = useQuery({
    queryKey: ["import-targets", task.id],
    queryFn: () =>
      api(`/tasks/${task.id}/import-targets`, z.array(targetSchema)),
    refetchInterval: 2000,
  });
  async function beginImport() {
    previewed.current = false;
    await beforeImport();
    const fresh = await api(`/tasks/${task.id}`, taskSchema);
    const target = await api(`/tasks/${task.id}/import-targets`, targetSchema, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: fresh.revision,
        idempotency_key: crypto.randomUUID(),
      }),
    });
    targetId.current = target.id;
  }
  async function receiving(kind: "upload" | "group" | "source", id: string) {
    if (!targetId.current)
      throw new Error("导入目标尚未固定，请重新打开入口。");
    const linked = await api(
      `/import-targets/${targetId.current}/resources`,
      targetSchema,
      { method: "POST", body: JSON.stringify({ kind, id }) },
    );
    targetId.current = linked.id;
    await recovery.refetch();
  }
  async function attach(
    asset: Pick<Asset, "id" | "name">,
    target = targetId.current,
    reviewed?: number,
  ) {
    if (!target) throw new Error("导入目标尚未固定，请从接入记录恢复。");
    const result = await api(
      `/import-targets/${target}/bind`,
      z.object({
        status: z.string(),
        task: taskSchema.optional(),
        error: z.object({ message: z.string() }).nullable(),
      }),
      {
        method: "POST",
        body: JSON.stringify({
          asset_id: asset.id,
          reviewed_revision: reviewed,
        }),
      },
    );
    await recovery.refetch();
    if (result.status !== "attached" || !result.task)
      throw new APIError(
        409,
        `“${asset.name}”已入库，未加入原研究：${result.error?.message ?? "请重试"}`,
        null,
        "IMPORT_BINDING_RECORDED",
      );
    onSynced(result.task);
    if (!previewed.current) {
      previewed.current = true;
      try { await onPreview?.(asset.id, result.task.id); }
      catch (failure) { setError(new Error(`资料已加入研究；预览或视图保存失败：${failure instanceof Error ? failure.message : "请从输入行重试查看"}`)); }
    }
    await cache.invalidateQueries({ queryKey: ["catalog", task.project_id] });
  }
  const [uploading, setUploading] = useState(false),
    [error, setError] = useState<unknown>(null);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const batches = useQuery({
    queryKey: ["imports", task.id],
    queryFn: () => api(`/tasks/${task.id}/imports`, z.array(batchSchema)),
    refetchInterval: (q) =>
      q.state.data?.some((b) =>
        b.items.some((i) => ["queued", "receiving"].includes(i.status)),
      )
        ? 600
        : false,
  });
  const pending =
    batches.data?.some((b) =>
      b.items.some((i) => ["queued", "receiving"].includes(i.status)),
    ) ?? false;
  const signature = (batches.data ?? [])
    .flatMap((b) => b.items.map((i) => i.id + ":" + i.status))
    .join("|");
  useEffect(() => {
    onBusy(uploading || pending);
  }, [uploading, pending, onBusy]);
  useEffect(() => {
    if (!signature || signature === lastSignature.current) return;
    lastSignature.current = signature;
    void api(`/tasks/${task.id}`, taskSchema)
      .then(onSynced)
      .then(() =>
        cache.invalidateQueries({ queryKey: ["assets", task.project_id] }),
      )
      .catch(setError);
  }, [signature, task.id, task.project_id, onSynced, cache]);
  const refresh = useCallback(async () => {
    await cache.invalidateQueries({ queryKey: ["imports", task.id] });
  }, [cache, task.id]);
  async function send(batchId: string, itemId: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    await api(`/imports/${batchId}/items/${itemId}/content`, itemSchema, {
      method: "POST",
      body: form,
    });
    await refresh();
  }
  return (
    <div className="research-import-panel">
      {mode !== "source" ? (
        <CatalogUpload
          inline
          project={task.project_id}
          disabled={uploading || pending}
          label="添加资料"
          beforeImport={beginImport}
          onBusy={setUploading}
          onReceiving={receiving}
          onAsset={async (asset) => {
            await attach(asset);
          }}
        />
      ) : null}
      <ErrorNotice error={error ?? batches.error ?? recovery.error} />
      {recovery.data?.flatMap((target) =>
        target.entries
          .filter((e) => e.asset_id && e.status !== "attached")
          .map((entry) => (
            <div
              key={target.id + entry.asset_id}
              className="pending-logical-row"
            >
              <strong>{entry.name}</strong> · 已入库，未加入研究
              {entry.error ? (
                <p className="error">{entry.error.message}</p>
              ) : null}
              <button
                type="button"
                disabled={uploading || pending}
                onClick={() =>
                  void (async () => {
                    try {
                      await beforeImport();
                      const fresh = await api(`/tasks/${task.id}`, taskSchema);
                      await attach(
                        { id: entry.asset_id!, name: entry.name ?? "资料" },
                        target.id,
                        fresh.revision,
                      );
                    } catch (failure) {
                      setError(failure);
                    }
                  })()
                }
              >
                核对后加入当前草稿
              </button>
            </div>
          )),
      )}
      <button
        hidden={!!mode}
        type="button"
        className="secondary"
        disabled={uploading || pending}
        onClick={() => setDirectoryOpen((value) => !value)}
      >
        {directoryOpen ? "收起本地资料" : "从已授权本地目录接入"}
      </button>
      {directoryOpen || mode === "source" ? (
        <SourceSnapshotPicker
          completedActionLabel="加入当前研究"
          project={task.project_id}
          beforeImport={beginImport}
          onReceiving={receiving}
          onAsset={async (asset) => {
            await attach(asset);
          }}
        />
      ) : null}
      {batches.data?.length ? (
        <details
          className="disclosure"
          open={expanded}
          onToggle={(event) => setExpanded(event.currentTarget.open)}
        >
          <summary>接入批次与恢复（{batches.data.length} 批）</summary>
          {batches.data.map((batch, index) => (
            <div key={batch.id}>
              <h3>
                批次 {batches.data.length - index} ·{" "}
                {batch.items.filter((i) => i.status === "ready").length}/
                {batch.items.length} 已接入
              </h3>
              <ul className="intake-items">
                {batch.items.map((item) => (
                  <li key={item.id}>
                    <div>
                      <strong>{item.source.name}</strong>
                      <p role="status">{labels[item.status] ?? item.status}</p>
                      {item.error ? (
                        <p className="error">{item.error.message}</p>
                      ) : null}
                    </div>
                    {["failed", "awaiting_upload"].includes(item.status) ? (
                      item.source.source_id ? (
                        <button
                          type="button"
                          className="secondary"
                          onClick={async () => {
                            try {
                              await api(
                                `/imports/${batch.id}/items/${item.id}/retry`,
                                batchSchema,
                                { method: "POST" },
                              );
                              await refresh();
                            } catch (e) {
                              setError(e);
                            }
                          }}
                        >
                          重试 {item.source.name}
                        </button>
                      ) : (
                        <label>
                          重选 {item.source.name}
                          <input
                            type="file"
                            disabled={uploading || pending}
                            onChange={async (event) => {
                              const file = event.target.files?.[0];
                              if (!file) return;
                              event.target.value = "";
                              setUploading(true);
                              setError(null);
                              try {
                                await beforeImport();
                                await send(batch.id, item.id, file);
                              } catch (e) {
                                setError(e);
                                await refresh();
                              } finally {
                                setUploading(false);
                              }
                            }}
                          />
                        </label>
                      )
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </details>
      ) : null}
    </div>
  );
}
