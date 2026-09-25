import { useState, useRef, useEffect, type ReactNode } from "react";
import { formatBytes } from "./formatBytes";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError, type Asset } from "./api";
import { SourceSnapshotPicker } from "./SourceSnapshotPicker";
import { Modal } from "./ManagedCatalog";
import {
  groupFiles,
  groupSchema,
  isSidecar,
  relativeName,
  uploadGroup,
  type UploadGroup,
} from "./groupUpload";
import { ErrorNotice } from "./shared";
import {
  uploadSchema,
  transfer,
  finishUpload,
  type UploadSession,
} from "./resumableUpload";

export function CatalogUpload({
  project,
  disabled,
  onAsset,
  beforeImport,
  onReceiving,
  onBusy,
  label = "导入资料",
  inline = false,
}: {
  project: string;
  disabled: boolean;
  onAsset: (asset: Asset, activate: boolean) => Promise<void>;
  beforeImport?: () => Promise<void>;
  onReceiving?: (
    kind: "upload" | "group" | "source",
    id: string,
  ) => Promise<void>;
  onBusy?: (busy: boolean) => void;
  label?: string;
  inline?: boolean;
}) {
  const transferController = useRef<AbortController | null>(null);
  useEffect(() => () => transferController.current?.abort(), []);
  const [open, setOpen] = useState(false);
  const [sourceMode, setSourceMode] = useState(false);
  const groups = useQuery({
    queryKey: ["upload-groups", project],
    queryFn: () =>
      api(`/projects/${project}/upload-groups`, z.array(groupSchema)),
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [progress, setProgress] = useState("");
  const [outcomes, setOutcomes] = useState<Record<string, string>>({});
  const outcome = (name: string, status: string) =>
    setOutcomes((rows) => ({ ...rows, [name]: status }));
  const pending = useQuery({
    queryKey: ["catalog-uploads", project],
    queryFn: () => api(`/projects/${project}/uploads`, z.array(uploadSchema)),
  });
  function report(state: UploadSession) {
    setProgress(
      `${state.name}：已接收 ${formatBytes(state.received_bytes)} / ${formatBytes(state.size)}`,
    );
  }
  async function upload(files: File[], resume?: UploadSession) {
    if (!files.length) return;
    transferController.current = new AbortController();
    setBusy(true);
    onBusy?.(true);
    setError(null);
    let activated = false;
    try {
      await beforeImport?.();
      for (const members of groupFiles(files)) {
        if (transferController.current?.signal.aborted) break;
        const file = members[0]!;
        const name = relativeName(file);
        let registered = false;
        outcome(name, "正在接收");
        try {
          if (
            !resume &&
            (members.length > 1 ||
              isSidecar(file.name) ||
              /\.(tiff?|shp)$/i.test(file.name))
          ) {
            const asset = await uploadGroup(
              project,
              members,
              report,
              undefined,
              transferController.current?.signal,
              onReceiving,
            );
            setProgress(`${asset.name}：逻辑资料已受管`);
            registered = true;
            await onAsset(asset, !activated);
            outcome(name, inline ? "已入库并加入研究" : "已入库");
            if (inline) setProgress("");
            activated = true;
            await groups.refetch();
            await pending.refetch();
            continue;
          }
          const session =
            resume ??
            (await api(`/projects/${project}/uploads`, uploadSchema, {
              method: "POST",
              body: JSON.stringify({
                name: file.name,
                size: file.size,
                idempotency_key: crypto.randomUUID(),
              }),
            }));
          await onReceiving?.("upload", session.id);
          report(session);
          await pending.refetch();
          const asset = await transfer(
            file,
            session,
            report,
            transferController.current?.signal,
          );
          setProgress(`${asset.name}：原件已受管`);
          registered = true;
          await onAsset(asset, !activated);
          outcome(name, inline ? "已入库并加入研究" : "已入库");
          if (inline) setProgress("");
          activated = true;
        } catch (failure) {
          if (
            failure instanceof APIError &&
            failure.code === "IMPORT_BINDING_RECORDED"
          ) {
            setOutcomes((rows) => {
              const next = { ...rows };
              delete next[name];
              return next;
            });
            setProgress("");
            continue;
          }
          outcome(
            name,
            registered
              ? "已入库，未加入研究；可从恢复记录继续"
              : failure instanceof Error && failure.name === "AbortError"
                ? "接收已暂停，可继续原文件"
                : failure instanceof APIError &&
                    failure.code === "SIDECAR_REQUIRES_PRIMARY"
                  ? "附件待关联"
                  : `未完成：${failure instanceof Error ? failure.message : "请重试"}`,
          );
          if (failure instanceof Error && failure.name === "AbortError")
            setProgress("文件尚未传完，已保留接收进度。");
          else if (!(
            failure instanceof APIError &&
            failure.code === "SIDECAR_REQUIRES_PRIMARY"
          ))
            setError(failure);
        }
        await pending.refetch();
      }
    } finally {
      setBusy(false);
      onBusy?.(false);
      await groups.refetch();
    }
  }
  async function resumeGroup(group: UploadGroup, files: File[]) {
    transferController.current = new AbortController();
    setBusy(true);
    onBusy?.(true);
    setError(null);
    try {
      await beforeImport?.();
      const asset = await uploadGroup(
        project,
        files,
        report,
        group,
        transferController.current?.signal,
        onReceiving,
      );
      await onAsset(asset, true);
      await pending.refetch();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
      onBusy?.(false);
      await groups.refetch();
    }
  }
  async function complete(session: UploadSession) {
    setBusy(true);
    setError(null);
    try {
      await beforeImport?.();
      await onReceiving?.("upload", session.id);
      await onAsset(await finishUpload(session), true);
      await pending.refetch();
    } catch (failure) {
      setError(failure);
    } finally {
      setBusy(false);
    }
  }
  async function cancel(session: UploadSession) {
    if (
      !window.confirm(
        "放弃未完成上传？只清理此会话的暂存分段，不影响原文件和已受管资料。",
      )
    )
      return;
    try {
      await api(`/uploads/${session.id}`, uploadSchema, { method: "DELETE" });
      await pending.refetch();
    } catch (failure) {
      setError(failure);
    }
  }
  return (
    <div className="catalog-upload">
      {!inline ? (
        <button type="button" disabled={disabled} onClick={() => setOpen(true)}>
          {label}
        </button>
      ) : null}
      {inline || open ? (
        <UploadSurface
          inline={inline}
          close={() => {
            transferController.current?.abort();
            setOpen(false);
          }}
        >
          {!inline ? (
            <div className="actions">
              <button
                type="button"
                className="secondary"
                aria-pressed={!sourceMode}
                onClick={() => setSourceMode(false)}
              >
                本机文件
              </button>
              <button
                type="button"
                className="secondary"
                aria-pressed={sourceMode}
                onClick={() => setSourceMode(true)}
              >
                已授权来源
              </button>
            </div>
          ) : null}
          {sourceMode ? (
            <SourceSnapshotPicker
              project={project}
              disabled={disabled || busy}
              beforeImport={beforeImport}
              onAsset={onAsset}
            />
          ) : null}
          <div
            hidden={sourceMode}
            aria-label="资料拖放区"
            onDragOver={(e) => {
              e.preventDefault();
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (!disabled && !busy)
                void upload(Array.from(e.dataTransfer.files));
            }}
          >
            <p>选择或拖入文件；同目录的影像、矢量主件与附件自动成组。</p>
            <label htmlFor="catalog-upload">选择并导入资料</label>
            <input
              id="catalog-upload"
              type="file"
              multiple
              disabled={disabled || busy}
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = "";
                void upload(files);
              }}
            />
            <label>
              选择资料文件夹
              <input
                type="file"
                multiple
                {...{ webkitdirectory: "" }}
                disabled={disabled || busy}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  event.target.value = "";
                  void upload(files);
                }}
              />
            </label>
            <ErrorNotice error={error ?? pending.error ?? groups.error} />
            {progress ? <p role="status">{progress}</p> : null}
            {Object.keys(outcomes).length ? (
              <ul aria-label="本批导入结果">
                {Object.entries(outcomes).map(([name, status]) => (
                  <li key={name}>
                    <strong>{name}</strong> · {status}
                  </li>
                ))}
              </ul>
            ) : null}
            {groups.data?.map((group) => (
              <PendingGroup
                key={group.id}
                group={group}
                busy={busy}
                resume={(files) => void resumeGroup(group, files)}
                associate={async (asset) => {
                  setBusy(true);
                  setError(null);
                  try {
                    const next = await api(
                      `/upload-groups/${group.id}/primary`,
                      groupSchema,
                      {
                        method: "POST",
                        body: JSON.stringify({
                          asset_id: asset.id,
                          revision: asset.revision,
                        }),
                      },
                    );
                    await resumeGroup(next, []);
                  } catch (failure) {
                    setError(failure);
                  } finally {
                    setBusy(false);
                    await groups.refetch();
                  }
                }}
              />
            ))}
            {pending.data?.length ? (
              <details open={!busy}>
                <summary>未完成接入（{pending.data.length}）</summary>
                {pending.data
                  .filter(
                    (session) =>
                      !groups.data?.some((group) =>
                        group.members.some(
                          (member) => member.upload_id === session.id,
                        ),
                      ),
                  )
                  .map((session) => (
                    <div key={session.id}>
                      <strong>{session.name}</strong>
                      <p>
                        {formatBytes(session.received_bytes)} /{" "}
                        {formatBytes(session.size)} 已保存
                      </p>
                      {session.error ? (
                        <p className="error">{session.error.message}</p>
                      ) : null}
                      {session.received_bytes === session.size ? (
                        <button
                          type="button"
                          disabled={disabled || busy}
                          onClick={() => void complete(session)}
                        >
                          继续提交 {session.name}
                        </button>
                      ) : (
                        <label>
                          重选原文件继续：{session.name}
                          <input
                            type="file"
                            disabled={disabled || busy}
                            onChange={(event) => {
                              const file = event.target.files?.[0];
                              event.target.value = "";
                              if (file) void upload([file], session);
                            }}
                          />
                        </label>
                      )}
                      <button
                        type="button"
                        className="secondary"
                        disabled={disabled || busy}
                        onClick={() => void cancel(session)}
                      >
                        放弃此上传
                      </button>
                    </div>
                  ))}
              </details>
            ) : null}
          </div>
        </UploadSurface>
      ) : null}
    </div>
  );
}

function UploadSurface({
  inline,
  close,
  children,
}: {
  inline: boolean;
  close: () => void;
  children: ReactNode;
}) {
  return inline ? (
    <>{children}</>
  ) : (
    <Modal title="导入项目资料" close={close}>
      {children}
    </Modal>
  );
}

const candidateSchema = z.array(
  z.object({
    id: z.string(),
    revision: z.number(),
    name: z.string(),
    size: z.number(),
  }),
);
function PendingGroup({
  group,
  busy,
  resume,
  associate,
}: {
  group: UploadGroup;
  busy: boolean;
  resume: (files: File[]) => void;
  associate: (asset: z.infer<typeof candidateSchema>[number]) => Promise<void>;
}) {
  const hasPrimary = group.members.some((m) =>
    /\.(tiff?|shp)$/i.test(m.relative_path),
  );
  const vector = group.members.some((m) =>
    /\.(shp|shx|dbf|prj|cpg|qix|sbn|sbx)$/i.test(m.relative_path),
  );
  const candidates = useQuery({
    queryKey: ["primary-candidates", group.project_id, group.id],
    enabled: !hasPrimary && !vector,
    queryFn: () =>
      api(`/upload-groups/${group.id}/primary-candidates`, candidateSchema),
  });
  return (
    <section className="pending-logical-row" aria-label="待恢复逻辑资料">
      <div>
        <strong>{group.members[0]?.relative_path}</strong> ·{" "}
        {hasPrimary
          ? "待完成接入"
          : vector
            ? "待补齐矢量组成员"
            : "附件待关联主影像"}
      </div>
      {!hasPrimary && candidates.data?.length ? (
        <>
          <p>发现可能对应的已导入影像，请核对后关联。</p>
          {candidates.data.map((a) => (
            <button
              type="button"
              key={a.id}
              disabled={busy}
              onClick={() => void associate(a)}
            >
              关联这份影像：{a.name} · 版本{a.revision}
            </button>
          ))}
        </>
      ) : null}
      <ErrorNotice error={candidates.error} />
      <label>
        {hasPrimary
          ? "重选未传完的文件"
          : vector
            ? "补选对应SHP及关联文件"
            : "补选对应影像"}
        <input
          type="file"
          multiple
          disabled={busy}
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            e.target.value = "";
            if (files.length) resume(files);
          }}
        />
      </label>
      {hasPrimary &&
      group.members.every((m) => m.upload.received_bytes === m.upload.size) ? (
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => resume([])}
        >
          重试登记
        </button>
      ) : null}
      <details>
        <summary>成员与接收详情（{group.members.length}）</summary>
        <ul>
          {group.members.map((m) => (
            <li key={m.upload_id}>
              {m.relative_path} · {formatBytes(m.upload.received_bytes)} /{" "}
              {formatBytes(m.upload.size)} {m.upload.error?.message}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
