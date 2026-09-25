import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema, jobSchema } from "./api";
import { taskSchema, type TaskRecord } from "./draft";
import { ConflictPanel } from "./ConflictPanel";
import { SemanticDefinition } from "./SemanticDefinition";
import { SourceStatement } from "./SourceStatement";
import { ImportPanel } from "./ImportPanel";
import type { DraftSummary } from "./ResearchHeader";
import { useTaskDraft, saveMessage } from "./useTaskDraft";
import { MethodSelector } from "./Methods";
import { TaskRuns } from "./TaskRuns";
import { TemporalEditor } from "./TemporalEditor";
import { ModelPreparation } from "./ModelPreparation";
import { ErrorNotice, purposes } from "./shared";
import { TaskAssetWorkspace } from "./TaskAssetWorkspace";
import { InputAttachmentClient } from "./inputAttachment";
import { AssetPicker } from "./AssetPicker";
const preflightSchema = z.object({
  ready: z.boolean(),
  issues: z.array(
    z
      .object({
        code: z.string(),
        message: z.string().optional(),
        field: z.string().optional(),
      })
      .passthrough(),
  ),
});
export function TaskWorkspace({
  initial,
  canEdit = true,
  onController,
  onDraftSummary,
  embedded = false,
}: {
  initial: TaskRecord;
  canEdit?: boolean;
  embedded?: boolean;
  onDraftSummary?: (summary: DraftSummary) => void;
  onController?: (
    controller: {
      save: () => Promise<void>;
      replace: (task: TaskRecord) => void;
      rename: (title: string) => Promise<void>;
      openAdd: (mode: "library" | "upload" | "source") => Promise<void>;
      removeInput: (id: string, revision: number) => Promise<void>;
    } | null,
  ) => void;
}) {
  const [attachmentClient] = useState(() => new InputAttachmentClient());
  const cache = useQueryClient();
  const { session, snapshot, task, replaceTask } = useTaskDraft(initial);
  const importDialog = useRef<HTMLDialogElement>(null);
  const importTrigger = useRef<HTMLElement | null>(null);
  const [addMode, setAddMode] = useState<"library" | "upload" | "source">(
    "upload",
  );
  useEffect(() => {
    onController?.({
      save: async () => {
        await session.save();
      },
      replace: replaceTask,
      openAdd: async (mode) => {
        await session.save();
        importTrigger.current =
          document.querySelector<HTMLButtonElement>(
            ".research-content-manager .content-input-tools button",
          ) ??
          (document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null);
        setAddMode(mode);
        importDialog.current?.showModal();
      },
      removeInput: async (id, revision) => {
        await session.save();
        if (session.snapshot().task.revision !== revision)
          throw new Error("草稿已变化，请重新核对移除影响");
        session.edit((draft) => ({
          ...draft,
          selection: draft.selection.filter((source) => source.asset_id !== id),
          mapping: draft.mapping.filter((binding) => binding.asset_id !== id),
        }));
        await session.save();
      },
      rename: async (title) => {
        session.edit((draft) => ({ ...draft, title }));
        await session.save();
      },
    });
    return () => onController?.(null);
  }, [onController, session, replaceTask]);
  useEffect(() => {
    onDraftSummary?.({
      taskId: task.id,
      title: task.draft.title,
      status: snapshot.status,
    });
  }, [onDraftSummary, task.id, task.draft.title, snapshot.status]);
  const [importing, setImporting] = useState(false);
  const beforeImport = useCallback(() => session.save(), [session]);
  const onImportSynced = useCallback(
    (saved: TaskRecord) => {
      if (
        session.snapshot().status === "saved" &&
        saved.revision >= session.snapshot().task.revision
      )
        replaceTask(saved);
    },
    [session, replaceTask],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [issues, setIssues] = useState<
    z.infer<typeof preflightSchema>["issues"]
  >([]);
  const assets = useQuery({
    queryKey: [
      "task-assets",
      task.id,
      task.draft.selection.map((ref) => ref.asset_id).join(":"),
    ],
    queryFn: () => api(`/tasks/${task.id}/assets`, z.array(assetSchema)),
  });
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const modelTask =
    task.draft.purpose === "cluster" || task.draft.purpose === "regression";
  const models = useQuery({
    queryKey: ["models", task.project_id],
    queryFn: () =>
      api(
        `/projects/${task.project_id}/models`,
        z.array(
          z.object({
            release: z.object({
              model_id: z.string(),
              package: z.string(),
              version: z.string(),
            }),
            release_digest: z.string(),
            approved: z.boolean(),
            can_approve: z.boolean(),
          }),
        ),
      ),
    enabled: modelTask,
  });
  const selected = assets.data ?? [];
  const changeMapping = (
    index: number,
    field: "unit" | "concept" | "support",
    text: string,
  ) =>
    session.edit((d) => ({
      ...d,
      mapping: d.mapping.map((m, i) =>
        i === index ? { ...m, [field]: text || null } : m,
      ),
    }));
  async function run() {
    setBusy(true);
    setError(null);
    try {
      await session.save();
      const current = session.snapshot().task;
      const check = await api(`/tasks/${task.id}/preflight`, preflightSchema);
      setIssues(check.issues);
      if (!check.ready) return;
      const created = await api(`/tasks/${task.id}/execute`, jobSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: current.revision,
          idempotency_key: crypto.randomUUID(),
        }),
      });
      setActiveRun(created.id);
      await cache.invalidateQueries({ queryKey: ["jobs", task.id] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {createPortal(
        <dialog
          ref={importDialog}
          className="catalog-modal"
          aria-label="添加研究输入"
          onClose={() => importTrigger.current?.focus()}
        >
          <div className="section-heading">
            <h2>添加资料</h2>
            <button
              type="button"
              className="secondary"
              onClick={() => importDialog.current?.close()}
            >
              关闭
            </button>
          </div>
          <div className="panel-tabs" role="group" aria-label="添加方式">
            {(["library", "upload", "source"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={addMode === mode ? "" : "secondary"}
                aria-pressed={addMode === mode}
                onClick={() => setAddMode(mode)}
              >
                {
                  {
                    library: "从资料库选择",
                    upload: "导入新资料",
                    source: "已授权来源",
                  }[mode]
                }
              </button>
            ))}
          </div>
          <fieldset className="task-controls" disabled={!canEdit}>
            {addMode === "library" ? (
              <AssetPicker
                initialOpen
                project={task.project_id}
                selection={task.draft.selection.map((ref) => ref.asset_id)}
                disabled={busy || importing || !canEdit}
                onSelect={async (assetId) => {
                  setBusy(true);
                  setError(null);
                  try {
                    await session.save();
                    const response = await attachmentClient.attachId(
                      session.snapshot().task,
                      assetId,
                    );
                    const item = response.items[0];
                    if (!item || item.status === "rejected")
                      throw new Error(item?.message ?? "资料未加入");
                    replaceTask(response.task);
                  } catch (error) {
                    setError(error);
                  } finally {
                    setBusy(false);
                  }
                }}
              />
            ) : (
              <ImportPanel
                mode={addMode}
                task={task}
                beforeImport={beforeImport}
                onSynced={onImportSynced}
                onBusy={setImporting}
              />
            )}
            <ErrorNotice error={error} />
          </fieldset>
        </dialog>,
        document.body,
      )}
      <fieldset
        data-processing-step="sources"
        className="task-controls"
        disabled={busy || importing || !canEdit}
      >
        {!embedded ? (
          <Link to={"/?project=" + task.project_id}>返回任务</Link>
        ) : null}
        {!embedded ? (
          <>
            <div className="section-heading">
              <h1>{purposes[task.draft.purpose]}</h1>
              <p
                role="status"
                className={snapshot.status === "saved" ? "saved" : "warning"}
              >
                {saveMessage(snapshot.status)}
              </p>
            </div>
            <label className="task-title">
              任务名称
              <input
                value={task.draft.title}
                disabled={busy || importing}
                onChange={(e) =>
                  session.edit((d) => ({ ...d, title: e.target.value }))
                }
              />
            </label>
          </>
        ) : null}
        <ErrorNotice error={error ?? snapshot.error ?? assets.error} />
        <ConflictPanel
          key={
            snapshot.conflicts.length
              ? JSON.stringify(snapshot.conflicts)
              : "none"
          }
          session={session}
          onResolved={() => setError(null)}
        />
        {snapshot.status === "error" ? (
          <button
            className="secondary"
            onClick={() => {
              void session.save().catch(setError);
            }}
          >
            重试保存
          </button>
        ) : null}
        {!embedded ? (
          <section>
            <h2>输入资料</h2>
            <p>
              选择文件后自动读取格式、图层、字段和空间信息，并绑定到当前任务。
            </p>
            <button
              type="button"
              className="secondary"
              onClick={(event) => {
                importTrigger.current = event.currentTarget;
                setAddMode("upload");
                importDialog.current?.showModal();
              }}
            >
              上传或接入资料
            </button>
            {busy ? <p role="status">正在处理当前操作，请稍候…</p> : null}
          </section>
        ) : null}
      </fieldset>
      <div hidden={embedded}>
        <TaskAssetWorkspace key={task.id} taskId={task.id} assets={selected} />
      </div>
      <fieldset
        className="task-controls"
        disabled={busy || importing || !canEdit}
      >
        <section data-processing-step="sources" aria-label="任务分析资料选择">
          {selected
            .filter((asset) => asset.facts.layers.length > 1)
            .map((asset) => (
              <label key={asset.id}>
                使用 {asset.name} 中的图层或表
                <select
                  value={
                    task.draft.selection.find(
                      (ref) => ref.asset_id === asset.id,
                    )?.layer ?? ""
                  }
                  onChange={(event) =>
                    session.edit((draft) => ({
                      ...draft,
                      selection: draft.selection.map((ref) =>
                        ref.asset_id === asset.id
                          ? { ...ref, layer: event.target.value || null }
                          : ref,
                      ),
                    }))
                  }
                >
                  <option value="">按任务选择实际图层（不自动取第一层）</option>
                  {asset.facts.layers.map((layer) => (
                    <option key={layer.name} value={layer.name}>
                      {layer.name}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          {!embedded ? (
            <AssetPicker
              project={task.project_id}
              selection={task.draft.selection.map((ref) => ref.asset_id)}
              disabled={busy || importing || !canEdit}
              onSelect={async (assetId) => {
                setBusy(true);
                try {
                  await session.save();
                  const response = await attachmentClient.attachId(
                    session.snapshot().task,
                    assetId,
                  );
                  const item = response.items[0];
                  if (!item) throw new Error("加入回执缺少资料项");
                  if (item.status === "rejected")
                    throw new Error(item.message ?? "资料未加入");
                  replaceTask(response.task);
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            />
          ) : null}
        </section>
        {selected.length ? (
          <details data-processing-step="sources">
            <summary>来源与使用声明</summary>
            <SourceStatement
              task={task}
              edit={(change) => session.edit(change)}
              save={async () => {
                await session.save();
                return session.snapshot().task;
              }}
              replaceTask={replaceTask}
              setBusy={setBusy}
            />
          </details>
        ) : null}
        {["assessment", "optimization"].includes(task.draft.purpose) ? (
          <div data-processing-step="normalization weights synthesis">
            <MethodSelector
              task={task}
              change={(change) => session.edit(change)}
            />
          </div>
        ) : null}
        {modelTask ? (
          <div data-processing-step="synthesis spatial">
            <ModelPreparation
              raster={
                selected.length > 0 &&
                selected.every((a) =>
                  ["geotiff", "cog"].includes(a.facts.profile),
                )
              }
              purpose={task.draft.purpose as "cluster" | "regression"}
              options={task.draft.options}
              change={(key, value) =>
                session.edit((d) => ({
                  ...d,
                  options: { ...d.options, [key]: value },
                }))
              }
            />
            <section>
              <h2>模型执行资格</h2>
              <ErrorNotice error={models.error} />
              {models.data?.map((model) => (
                <div key={model.release.model_id}>
                  <p>
                    {model.release.package} {model.release.version} ·
                    原包技术核验通过 ·{" "}
                    {model.approved
                      ? "本项目已批准当前版本"
                      : "本项目尚未批准当前版本"}
                  </p>
                  {!model.approved && model.can_approve ? (
                    <button
                      className="secondary"
                      disabled={busy || importing}
                      onClick={async () => {
                        try {
                          await api(
                            `/projects/${task.project_id}/models/${model.release.model_id}/approve`,
                            z.unknown(),
                            {
                              method: "POST",
                              body: JSON.stringify({
                                release_digest: model.release_digest,
                              }),
                            },
                          );
                          await cache.invalidateQueries({
                            queryKey: ["models", task.project_id],
                          });
                        } catch (e) {
                          setError(e);
                        }
                      }}
                    >
                      项目负责人批准 {model.release.package}
                    </button>
                  ) : null}
                </div>
              ))}
            </section>
          </div>
        ) : null}
        {selected.length === 1 &&
        ["csv", "csvw"].includes(selected[0]!.facts.profile) &&
        ["assessment", "optimization"].includes(task.draft.purpose) ? (
          <details data-processing-step="spatial">
            <summary>观测表的实际坐标关联（可选）</summary>
            <p>
              有明确坐标字段和坐标系时才关联；未关联的表正常进行数值计算，不生成地理位置。
            </p>
            <label>
              <input
                type="checkbox"
                checked={!!task.draft.options.spatial_reference}
                onChange={(event) =>
                  session.edit((d) => {
                    const options = { ...d.options };
                    if (event.target.checked)
                      options.spatial_reference = {
                        x_field: "",
                        y_field: "",
                        crs: "",
                      };
                    else delete options.spatial_reference;
                    return { ...d, options };
                  })
                }
              />
              关联实际坐标
            </label>
            {task.draft.options.spatial_reference ? (
              <div className="form-grid">
                {(["x_field", "y_field", "crs"] as const).map((key) => {
                  const labels = {
                    x_field: "经度或X字段",
                    y_field: "纬度或Y字段",
                    crs: "坐标系（来自资料依据）",
                  };
                  const reference = task.draft.options
                    .spatial_reference as Record<string, string>;
                  const change = (value: string) =>
                    session.edit((d) => ({
                      ...d,
                      options: {
                        ...d.options,
                        spatial_reference: { ...reference, [key]: value },
                      },
                    }));
                  return (
                    <label key={key}>
                      {labels[key]}
                      {key === "crs" ? (
                        <input
                          value={reference[key] ?? ""}
                          onChange={(event) => change(event.target.value)}
                          placeholder="例如 EPSG:4326，以实际资料为准"
                        />
                      ) : (
                        <select
                          value={reference[key] ?? ""}
                          onChange={(event) => change(event.target.value)}
                        >
                          <option value="">请选择实际字段</option>
                          {selected[0]!.facts.layers.flatMap((layer) =>
                            layer.fields.map((field) => (
                              <option
                                key={layer.name + "/" + field.name}
                                value={layer.name + "/" + field.name}
                              >
                                {layer.name} / {field.name}
                              </option>
                            )),
                          )}
                        </select>
                      )}
                    </label>
                  );
                })}
              </div>
            ) : null}
          </details>
        ) : null}
        {task.draft.mapping.length > 0 ? (
          <section data-processing-step="indicators">
            <h3>指标与来源字段</h3>

            <fieldset className="task-controls" disabled={busy || importing}>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>源字段</th>
                      <th>本次用途</th>
                      <th>科学含义</th>
                      <th>单位</th>
                      <th>支撑</th>
                      <th>依据</th>
                    </tr>
                  </thead>
                  <tbody>
                    {task.draft.mapping.map((m, index) => (
                      <tr key={m.asset_id + m.field}>
                        <td>
                          <span>
                            {
                              selected.find((asset) => asset.id === m.asset_id)
                                ?.name
                            }
                          </span>
                          <br />
                          {m.field}
                        </td>
                        <td>
                          <select
                            aria-label={`用途 ${m.field}`}
                            value={m.role}
                            onChange={(e) => {
                              const role =
                                taskSchema.shape.draft.shape.mapping.element.shape.role.parse(
                                  e.target.value,
                                );
                              session.edit((d) => ({
                                ...d,
                                mapping: d.mapping.map((b, i) =>
                                  i === index ? { ...b, role } : b,
                                ),
                              }));
                            }}
                          >
                            <option value="feature">
                              {modelTask ? "解释变量" : "计算指标"}
                            </option>
                            {task.draft.purpose === "regression" ||
                            m.role === "response" ? (
                              <option value="response">响应变量</option>
                            ) : null}
                            <option value="identity">观测标识</option>
                            <option value="ignored">本次不使用</option>
                            <option value="time">时间</option>
                            <option value="geometry">几何</option>
                            <option value="constraint">约束</option>
                          </select>
                        </td>
                        <td>
                          <input
                            disabled={
                              !["feature", "response", "constraint"].includes(
                                m.role,
                              )
                            }
                            aria-label={`科学含义 ${m.field}`}
                            value={m.concept ?? ""}
                            onChange={(e) =>
                              changeMapping(index, "concept", e.target.value)
                            }
                          />
                        </td>
                        <td>
                          <input
                            disabled={!["feature", "response"].includes(m.role)}
                            aria-label={`单位 ${m.field}`}
                            value={m.unit ?? ""}
                            onChange={(e) =>
                              changeMapping(index, "unit", e.target.value)
                            }
                          />
                        </td>
                        <td>
                          <select
                            aria-label={`支撑 ${m.field}`}
                            value={m.support ?? ""}
                            onChange={(e) =>
                              changeMapping(index, "support", e.target.value)
                            }
                          >
                            <option value="">待确认</option>
                            <option value="point">时刻/观测点</option>
                            <option value="interval">时间区间</option>
                            <option value="grid">栅格像元</option>
                            <option value="management_unit">管理单元</option>
                          </select>
                        </td>
                        <td>
                          {m.template_id
                            ? `认可模板 v${m.template_revision}`
                            : "文件/本次声明"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </fieldset>
            <SemanticDefinition
              task={task}
              assets={selected}
              edit={(change) => session.edit(change)}
              save={async () => {
                await session.save();
                return session.snapshot().task;
              }}
              replaceTask={replaceTask}
              setBusy={setBusy}
            />
          </section>
        ) : null}
        {task.draft.purpose === "temporal" ? (
          <div data-processing-step="spatial">
            <TemporalEditor
              draft={task.draft}
              assets={selected}
              onChange={(next) => session.edit(() => next)}
            />
          </div>
        ) : null}
        {!embedded ? (
          <section data-processing-step="synthesis validation">
            <div className="section-heading">
              <h2>预检与实际执行</h2>
              <button
                disabled={
                  busy || snapshot.status === "error" || selected.length === 0
                }
                onClick={() => {
                  void run();
                }}
              >
                预检并执行
              </button>
            </div>
            {issues.length ? (
              <ul className="issues">
                {issues.map((issue, index) => (
                  <li key={index}>
                    {issue.message ?? issue.code}
                    {issue.field ? `：${issue.field}` : ""}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        ) : null}
      </fieldset>
      {!embedded ? (
        <TaskRuns
          key={activeRun ?? task.id}
          taskId={task.id}
          draftRevision={task.revision}
          canEdit={canEdit}
        />
      ) : null}
    </>
  );
}
