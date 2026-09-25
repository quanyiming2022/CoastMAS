import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { api } from "./api";
import { ErrorNotice } from "./shared";
const metadataSchema = z.object({
  revision: z.number(),
  display_name: z.string(),
  description: z.string(),
  tags: z.array(z.string()),
});
const previewSchema = z.object({
  id: z.string(),
  total: z.number(),
  items: z.array(
    z.object({
      id: z.string(),
      display_name: z.string(),
      references: z.object({
        active_runs: z.array(z.string()),
        task_references: z.number(),
      }),
    }),
  ),
});
const appliedSchema = z.object({
  items: z.array(
    z.object({
      id: z.string(),
      status: z.string(),
      message: z.string().optional(),
    }),
  ),
});
export type CatalogSelection =
  | { ids: string[] }
  | {
      query: { query: string; sort: string; state: string; profile: string };
      excluded_ids: string[];
    };
export function MetadataEditor({
  assetId,
  onClose,
  onSaved,
}: {
  assetId: string;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [metadata, setMetadata] = useState<z.infer<
      typeof metadataSchema
    > | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    ref.current?.showModal();
    let active = true;
    void api(`/assets/${assetId}/metadata`, metadataSchema)
      .then((v) => {
        if (active) setMetadata(v);
      })
      .catch((e) => {
        if (active) setError(e);
      });
    return () => {
      active = false;
    };
  }, [assetId]);
  return (
    <dialog
      ref={ref}
      className="catalog-dialog"
      aria-label="修改目录信息"
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!metadata) return;
          setBusy(true);
          setError(null);
          try {
            await api(`/assets/${assetId}/metadata`, metadataSchema, {
              method: "PATCH",
              body: JSON.stringify({
                expected_revision: metadata.revision,
                display_name: metadata.display_name,
                description: metadata.description,
                tags: metadata.tags,
              }),
            });
            await onSaved();
            ref.current?.close();
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>修改目录信息</h2>

        <ErrorNotice error={error} />
        {metadata ? (
          <>
            <label>
              显示名称
              <input
                required
                maxLength={240}
                value={metadata.display_name}
                onChange={(e) =>
                  setMetadata({ ...metadata, display_name: e.target.value })
                }
              />
            </label>
            <label>
              说明
              <textarea
                maxLength={4000}
                value={metadata.description}
                onChange={(e) =>
                  setMetadata({ ...metadata, description: e.target.value })
                }
              />
            </label>
            <label>
              标签（逗号分隔）
              <input
                value={metadata.tags.join(",")}
                onChange={(e) =>
                  setMetadata({
                    ...metadata,
                    tags: e.target.value.split(/[,，]/),
                  })
                }
              />
            </label>
          </>
        ) : (
          <p role="status">正在读取目录信息…</p>
        )}
        <div className="actions">
          <button type="submit" disabled={!metadata || busy}>
            {busy ? "正在保存…" : "保存修改"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => ref.current?.close()}
          >
            取消
          </button>
        </div>
      </form>
    </dialog>
  );
}
export function CatalogOperation({
  project,
  action,
  selection,
  onClose,
  onSaved,
}: {
  project: string;
  action: "recycle" | "restore";
  selection: CatalogSelection;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    started = useRef(false);
  const [preview, setPreview] = useState<z.infer<typeof previewSchema> | null>(
      null,
    ),
    [result, setResult] = useState<z.infer<typeof appliedSchema> | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  useEffect(() => {
    ref.current?.showModal();
    if (started.current) return;
    started.current = true;
    void api(`/projects/${project}/catalog/operations`, previewSchema, {
      method: "POST",
      body: JSON.stringify({ action, selection }),
    })
      .then(setPreview)
      .catch(setError);
  }, [project, action, selection]);
  const label = action === "recycle" ? "回收" : "恢复";
  return (
    <dialog
      ref={ref}
      className="catalog-dialog"
      aria-label={`${label}资料`}
      onClose={onClose}
    >
      <h2>{label}资料</h2>
      <ErrorNotice error={error} />
      {preview ? (
        <>
          <p>
            本次固定选择 {preview.total}{" "}
            项。原始文件和历史引用保留；执行前会重新核对版本、权限和运行状态。
          </p>
          <div className="operation-preview">
            <ul>
              {preview.items.map((item) => (
                <li key={item.id}>
                  {item.display_name}
                  {item.references.active_runs.length
                    ? " · 正在运行，暂不能回收"
                    : item.references.task_references
                      ? ` · ${item.references.task_references} 个任务引用将保留`
                      : ""}
                </li>
              ))}
            </ul>
          </div>
        </>
      ) : !error ? (
        <p role="status">正在核对影响…</p>
      ) : null}
      {result ? (
        <div role="status">
          <p>
            {result.items.filter((i) => i.status === "applied").length} 项已
            {label}；{result.items.filter((i) => i.status !== "applied").length}{" "}
            项未执行。
          </p>
          <ul>
            {result.items
              .filter((i) => i.status !== "applied")
              .map((i) => (
                <li key={i.id}>
                  {preview?.items.find((p) => p.id === i.id)?.display_name}：
                  {i.message}
                </li>
              ))}
          </ul>
        </div>
      ) : null}
      <div className="actions">
        {!result ? (
          <button
            type="button"
            disabled={!preview || !preview.total || busy}
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                setResult(
                  await api(
                    `/projects/${project}/catalog/operations/${preview!.id}/apply`,
                    appliedSchema,
                    { method: "POST" },
                  ),
                );
                await onSaved();
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "正在执行…" : `确认${label}`}
          </button>
        ) : null}
        <button
          type="button"
          className="secondary"
          onClick={() => ref.current?.close()}
        >
          {result ? "完成" : "取消"}
        </button>
      </div>
    </dialog>
  );
}
