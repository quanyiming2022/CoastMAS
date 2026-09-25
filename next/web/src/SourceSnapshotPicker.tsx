import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError, assetSchema, type Asset } from "./api";
import { ErrorNotice } from "./shared";
import { useCatalogSearch } from "./catalogSearch";
const itemSchema = z.object({
  id: z.string(),
  status: z.string(),
  asset_id: z.string().nullable(),
  members: z.array(z.object({ path: z.string() })),
  error: z.object({ message: z.string() }).nullable(),
});
const states: Record<string, string> = {
  queued: "排队中",
  copying: "正在建立受管快照",
  ready: "已进入资料库",
  failed: "接入失败",
};
export function SourceSnapshotPicker({
  project,
  onAsset,
  disabled = false,
  beforeImport,
  onReceiving,
  completedActionLabel = "查看已导入资料",
}: {
  project: string;
  onAsset: (asset: Asset, activate: boolean) => Promise<void>;
  disabled?: boolean;
  completedActionLabel?: string;
  beforeImport?: () => Promise<void>;
  onReceiving?: (
    kind: "upload" | "group" | "source",
    id: string,
  ) => Promise<void>;
}) {
  const roots = useQuery({
    queryKey: ["local-sources", project],
    queryFn: () =>
      api(
        `/projects/${project}/local-sources`,
        z.array(
          z.object({ id: z.string(), name: z.string(), granted: z.boolean() }),
        ),
      ),
  });
  const [choice, setChoice] = useState(""),
    [path, setPath] = useState(""),
    [offset, setOffset] = useState(0),
    [selected, setSelected] = useState<string[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const search = useCatalogSearch(),
    source = choice || roots.data?.find((r) => r.granted)?.id || "";
  const files = useQuery({
    queryKey: ["source-files", project, source, path, offset, search.query],
    enabled: !!source,
    queryFn: () =>
      api(
        `/projects/${project}/local-sources/${source}/files?${new URLSearchParams({ path, offset: String(offset), search: search.query })}`,
        z.object({
          items: z.array(
            z.object({
              name: z.string(),
              path: z.string(),
              directory: z.boolean(),
              size: z.number(),
            }),
          ),
          total: z.number(),
          limit: z.number(),
        }),
      ),
  });
  const jobs = useQuery({
    queryKey: ["source-snapshots", project],
    queryFn: () =>
      api(`/projects/${project}/source-snapshots`, z.array(itemSchema)),
    refetchInterval: (query) =>
      query.state.data?.some((j) => ["queued", "copying"].includes(j.status))
        ? 1000
        : false,
  });
  const callbacks = useRef(
    new Map<string, (asset: Asset, activate: boolean) => Promise<void>>(),
  );
  const [watched, setWatched] = useState<string[]>([]),
    notified = useRef(new Set<string>()),
    intent = useRef<{ key: string; body: string } | null>(null);
  useEffect(() => {
    for (const job of jobs.data ?? []) {
      if (
        job.status === "ready" &&
        job.asset_id &&
        watched.includes(job.id) &&
        !notified.current.has(job.id)
      ) {
        notified.current.add(job.id);
        void api(`/assets/${job.asset_id}`, assetSchema)
          .then((asset) =>
            (callbacks.current.get(job.id) ?? onAsset)(asset, true),
          )
          .catch((failure) => {
            if (!(
              failure instanceof APIError &&
              failure.code === "IMPORT_BINDING_RECORDED"
            ))
              setError(failure);
          });
      }
    }
  }, [jobs.data, watched, onAsset]);
  function directory(next: string) {
    setPath(next);
    setOffset(0);
    setSelected([]);
    search.change("");
  }
  async function queue() {
    setBusy(true);
    setError(null);
    try {
      await beforeImport?.();
      const body = JSON.stringify({ source_id: source, paths: selected });
      if (!intent.current || intent.current.body !== body)
        intent.current = { key: crypto.randomUUID(), body };
      const response = await api(
        `/projects/${project}/source-snapshots`,
        z.object({ items: z.array(itemSchema) }),
        {
          method: "POST",
          body: JSON.stringify({
            ...(JSON.parse(body) as { source_id: string; paths: string[] }),
            idempotency_key: intent.current.key,
          }),
        },
      );
      for (const item of response.items) {
        await onReceiving?.("source", item.id);
        callbacks.current.set(item.id, onAsset);
      }
      setWatched(response.items.map((i) => i.id));
      setSelected([]);
      intent.current = null;
      await jobs.refetch();
    } catch (failure) {
      if (!(
        failure instanceof APIError &&
        failure.code === "IMPORT_BINDING_RECORDED"
      ))
        setError(failure);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="source-snapshot-picker" aria-label="已授权来源导入">
      <p>
        选择文件后明确导入；系统建立固定快照，关闭页面后继续。TIFF附件自动成组，源目录变化不会改写资料库。
      </p>
      <ErrorNotice error={error ?? roots.error ?? files.error ?? jobs.error} />
      {!roots.isPending && !roots.data?.some((r) => r.granted) ? (
        <p>
          此项目尚无已授权来源。连接配置不等于项目授权，可在项目管理的来源页核对。
        </p>
      ) : null}
      {source ? (
        <>
          <div className="source-picker-toolbar">
            <label>
              授权来源
              <select
                value={source}
                disabled={busy}
                onChange={(e) => {
                  setChoice(e.target.value);
                  directory("");
                }}
              >
                {roots.data
                  ?.filter((r) => r.granted)
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              搜索当前目录
              <input
                type="search"
                value={search.text}
                onCompositionStart={() => search.compose(true)}
                onCompositionEnd={() => search.compose(false)}
                onChange={(e) => {
                  search.change(e.target.value);
                  setOffset(0);
                  setSelected([]);
                }}
              />
            </label>
            <button
              type="button"
              className="secondary"
              disabled={!path || busy}
              onClick={() => directory(path.split("/").slice(0, -1).join("/"))}
            >
              上级
            </button>
          </div>
          <p>
            目录：{path || "/"} · 已选 {selected.length} 项
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>选择</th>
                  <th>名称</th>
                  <th>大小</th>
                </tr>
              </thead>
              <tbody>
                {files.data?.items.map((file) => (
                  <tr key={file.path}>
                    <td>
                      {!file.directory ? (
                        <input
                          type="checkbox"
                          aria-label={`选择 ${file.name}`}
                          checked={selected.includes(file.path)}
                          onChange={(e) =>
                            setSelected(
                              e.target.checked
                                ? [...selected, file.path]
                                : selected.filter((p) => p !== file.path),
                            )
                          }
                        />
                      ) : null}
                    </td>
                    <td>
                      {file.directory ? (
                        <button
                          type="button"
                          className="secondary"
                          onClick={() => directory(file.path)}
                        >
                          {file.name}/
                        </button>
                      ) : (
                        <span title={file.path}>{file.name}</span>
                      )}
                    </td>
                    <td>
                      {file.directory
                        ? "—"
                        : (file.size / 1024 ** 2).toFixed(2) + " MiB"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={!offset}
              onClick={() => setOffset(offset - 100)}
            >
              上一页
            </button>
            <span>{files.data?.total ?? "—"} 项</span>
            <button
              type="button"
              className="secondary"
              disabled={!files.data || offset + 100 >= files.data.total}
              onClick={() => setOffset(offset + 100)}
            >
              下一页
            </button>
            <button
              type="button"
              disabled={busy || disabled || !selected.length}
              onClick={() => void queue()}
            >
              导入选中资料
            </button>
          </div>
        </>
      ) : null}
      {jobs.data?.length ? (
        <details open>
          <summary>来源接入记录</summary>
          <ul className="source-snapshot-records">
            {jobs.data.map((job) => (
              <li key={job.id}>
                <span>
                  {job.members[0]?.path} · {states[job.status] ?? job.status}
                </span>
                {job.error ? (
                  <span role="alert">{job.error.message}</span>
                ) : null}
                {job.status === "failed" ? (
                  <button
                    type="button"
                    className="secondary"
                    disabled={disabled}
                    onClick={() =>
                      void api(
                        `/source-snapshots/${job.id}/retry`,
                        z.object({ queued: z.boolean() }),
                        { method: "POST" },
                      )
                        .then(() => jobs.refetch())
                        .catch(setError)
                    }
                  >
                    重试原快照
                  </button>
                ) : null}
                {job.asset_id ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      void (async () => {
                        await beforeImport?.();
                        await onReceiving?.("source", job.id);
                        return api(`/assets/${job.asset_id}`, assetSchema);
                      })()
                        .then((asset) => onAsset(asset, true))
                        .catch(setError)
                    }
                  >
                    {completedActionLabel}
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
