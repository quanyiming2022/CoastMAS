import { PlanningUnitPreparation } from "./PlanningUnitPreparation";
import { PlanningTaskBindings } from "./PlanningTaskBindings";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema, jobSchema } from "./api";
import type { TaskRecord } from "./draft";
import type { ResearchStep } from "./ResearchPanels";
import type { DraftSummary } from "./ResearchHeader";
import { useTaskDraft } from "./useTaskDraft";
import { InputAttachmentClient } from "./inputAttachment";
import { AssetPicker } from "./AssetPicker";
import { ImportPanel } from "./ImportPanel";
import { ErrorNotice } from "./shared";
import { ConflictPanel } from "./ConflictPanel";
import { InputRequirements } from "./InputRequirements";
import { SourceStatement } from "./SourceStatement";
import { IndicatorSelector } from "./IndicatorSelector";
import { ProcessingStep } from "./ProcessingStep";
import { MethodSelector } from "./Methods";
import { TemporalEditor } from "./TemporalEditor";
export type ResearchEditorController = {
  save: () => Promise<void>;
  replace: (task: TaskRecord) => void;
  rename: (title: string) => Promise<void>;
  openAdd: (mode: "library" | "upload" | "source") => Promise<void>;
  removeInput: (id: string, revision: number) => Promise<void>;
};
/** One persistent draft controller; step children are independent, never a task page. */
export function ResearchEditor({
  initial,
  canEdit,
  step,
  onController,
  onDraftSummary,
  onRun,
  onExecute,
  onPreview,
}: {
  initial: TaskRecord;
  canEdit: boolean;
  step: ResearchStep | null;
  onController: (controller: ResearchEditorController | null) => void;
  onDraftSummary: (summary: DraftSummary) => void;
  onRun: (job: z.infer<typeof jobSchema>) => void;
  onExecute: () => void;
  onPreview?: (assetId: string, taskId: string) => Promise<void>;
}) {
  const [attachmentClient] = useState(() => new InputAttachmentClient());
  const { session, snapshot, task, replaceTask } = useTaskDraft(initial);
  const [importOpen, setImportOpen] = useState(false);
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
        setImportOpen(true);
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
        saved.id === session.snapshot().task.id &&
        session.snapshot().status === "saved" &&
        saved.revision >= session.snapshot().task.revision
      )
        replaceTask(saved);
    },
    [session, replaceTask],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const assets = useQuery({
    queryKey: [
      "task-assets",
      task.id,
      task.draft.selection.map((ref) => ref.asset_id).join(":"),
    ],
    queryFn: () => api(`/tasks/${task.id}/assets`, z.array(assetSchema)),
  });

  const saved = async () => {
    await session.save();
    return session.snapshot().task;
  };
  const input = assets.data ?? [];
  return (
    <>
      {createPortal(
        <dialog
          ref={importDialog}
          className="catalog-modal"
          aria-label="添加研究输入"
          onClose={() => {
            setImportOpen(false);
            importTrigger.current?.focus();
          }}
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
          {importOpen ? (
            <>
              <InputRequirements task={task} />
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
                        await onPreview?.(assetId, response.task.id);
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
                    onPreview={onPreview}
                    onBusy={setImporting}
                  />
                )}
                <ErrorNotice error={error} />
              </fieldset>
            </>
          ) : null}
        </dialog>,
        document.body,
      )}

      <ErrorNotice error={snapshot.error ?? error ?? assets.error} />
      <ConflictPanel session={session} onResolved={() => setError(null)} />
      {snapshot.status === "error" ? (
        <button
          type="button"
          onClick={() => void session.save().catch(setError)}
        >
          重试保存
        </button>
      ) : null}
      <fieldset
        className="task-controls"
        disabled={!canEdit || busy || importing}
      >
        {task.draft.options.task_type === "planning" && step === "objectives" ? <PlanningTaskBindings task={task} kind="objectives" canEdit={canEdit} onSaved={replaceTask} beforeSave={()=>session.save()}/> : null}
        {task.draft.options.task_type === "planning" && step === "constraints" ? <><PlanningTaskBindings task={task} kind="constraints" canEdit={canEdit} onSaved={replaceTask} beforeSave={()=>session.save()}/><PlanningTaskBindings task={task} kind="decisions" canEdit={canEdit} onSaved={replaceTask} beforeSave={()=>session.save()}/></> : null}
        {step === "sources" && input.length ? (
          <details>
            <summary>来源与使用声明</summary>
            <SourceStatement
              task={task}
              edit={(f) => session.edit(f)}
              save={saved}
              replaceTask={replaceTask}
              setBusy={setBusy}
            />
          </details>
        ) : null}
        {step === "spatial" && task.draft.options.task_type === "planning" ? <PlanningUnitPreparation task={task} assets={input} edit={f=>session.edit(f)} save={saved} onRun={onRun}/> : null}
        {step === "spatial" ? (
          <ProcessingStep
            operator="align_grid"
            task={task}
            assets={input}
            edit={(f) => session.edit(f)}
            save={saved}
            onRun={onRun}
          />
        ) : null}
        {step === "spatial" && task.draft.purpose === "temporal" ? (
          <TemporalEditor
            draft={task.draft}
            assets={input}
            onChange={(draft) => session.edit(() => draft)}
          />
        ) : null}
        {step === "indicators" ? (
          <IndicatorSelector
            task={task}
            save={saved}
            replace={replaceTask}
            onRun={onRun}
            onAddData={() => {
              void saved()
                .then(() => {
                  setAddMode("upload");
                  setImportOpen(true);
                  importDialog.current?.showModal();
                })
                .catch(setError);
            }}
          />
        ) : null}
        {(step === "normalization" || step === "weights") &&
        ["assessment", "optimization"].includes(task.draft.purpose) ? (
          <MethodSelector task={task} change={(f) => session.edit(f)} />
        ) : null}
        {step === "synthesis" ? (
          <button
            type="button"
            disabled={!task.draft.selection.length}
            onClick={onExecute}
          >
            运行综合计算
          </button>
        ) : null}
      </fieldset>
    </>
  );
}
