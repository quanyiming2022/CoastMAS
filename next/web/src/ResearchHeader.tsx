import { useId, useRef, useState } from "react";
import { APIError } from "./api";
import { Modal } from "./ManagedCatalog";
import { ErrorNotice } from "./shared";
import type { DraftSession } from "./draft";
export type DraftSummary = {
  taskId: string;
  title: string;
  status: ReturnType<DraftSession["snapshot"]>["status"];
};
export function researchSaveStatus(
  ready: boolean,
  saving: boolean,
  error: unknown,
  draftStatus: DraftSummary["status"] | null,
) {
  if (
    draftStatus === "conflict" ||
    (error instanceof APIError && error.status === 409)
  )
    return "保存冲突";
  if (error || draftStatus === "error") return "保存失败";
  if (!ready || draftStatus === null) return "正在恢复…";
  if (saving || draftStatus === "saving") return "保存中…";
  return draftStatus === "saved" ? "已保存" : "尚未保存";
}
export function combineSaveStatus(science: string, view: string) {
  return (
    ["保存冲突", "保存失败", "正在恢复…", "尚未保存", "保存中…"].find(
      (value) => science === value || view === value,
    ) ?? "已保存"
  );
}
export function ResearchHeader({
  title,
  status,
  statusDetail,
  canEdit,
  canExecute,
  onNew,
  onExecute,
  onRename,
}: {
  title: string;
  status: string;
  statusDetail?: string;
  canEdit: boolean;
  canExecute: boolean;
  onNew: () => void;
  onExecute: () => void;
  onRename?: (title: string) => Promise<void>;
}) {
  const [editingTitle, setEditingTitle] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const titleInputId = useId();
  const titleButton = useRef<HTMLButtonElement>(null);
  function close() {
    setEditingTitle(null);
    requestAnimationFrame(() => titleButton.current?.focus());
  }
  return (
    <div className="research-context">
      <h1>
        <button
          ref={titleButton}
          type="button"
          className="research-title-button secondary"
          title={title}
          aria-label="查看或编辑研究名称"
          disabled={!onRename}
          onClick={() => {
            setEditingTitle(title);
            setError(null);
          }}
        >
          {title}
        </button>
      </h1>
      <span
        role="status"
        className="research-save-status"
        data-state={status}
        title={
          statusDetail ??
          "草稿与研究现场的保存状态；不代表历史成果已按当前配置重新计算。"
        }
      >
        {status}
      </span>
      <button
        type="button"
        className="secondary research-new"
        disabled={!canEdit}
        onClick={onNew}
      >
        新建研究
      </button>
      <button
        type="button"
        className="research-execute"
        disabled={!canExecute}
        onClick={onExecute}
      >
        预检并执行
      </button>
      {editingTitle !== null ? (
        <Modal title="研究名称" close={close}>
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (!canEdit || !onRename) return;
              setPending(true);
              try {
                await onRename(editingTitle);
                close();
              } catch (problem) {
                setError(problem);
              } finally {
                setPending(false);
              }
            }}
          >
            <label htmlFor={titleInputId}>完整研究名称</label>
            <textarea
              id={titleInputId}
              required
              readOnly={!canEdit}
              value={editingTitle}
              onChange={(event) => setEditingTitle(event.target.value)}
            />
            <ErrorNotice error={error} />
            {canEdit ? (
              <button type="submit" disabled={pending || !editingTitle.trim()}>
                {pending ? "保存中…" : "保存名称"}
              </button>
            ) : null}
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
