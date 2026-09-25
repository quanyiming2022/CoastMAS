import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import { useBlocker } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, APIError } from "./api";
import { equalDraftValue } from "./merge";
import {
  DraftSession,
  RemoteDraftConflict,
  taskSchema,
  type TaskRecord,
} from "./draft";

export type AdditionalSaveGuard = { dirty: boolean; save: () => Promise<void> };

export function useTaskDraft(
  initial: TaskRecord,
  extraGuard?: AdditionalSaveGuard | null,
) {
  const cache = useQueryClient();
  const [session] = useState(
    () =>
      new DraftSession(initial, async (draft, revision) => {
        let saved: TaskRecord;
        try {
          saved = await api(`/tasks/${initial.id}`, taskSchema, {
            method: "PUT",
            body: JSON.stringify({ expected_revision: revision, draft }),
          });
        } catch (error) {
          if (!(error instanceof APIError) || error.code !== "DRAFT_CONFLICT") throw error;
          const remote = await api(`/tasks/${initial.id}`, taskSchema);
          if (!equalDraftValue(remote.draft, draft))
            throw new RemoteDraftConflict(remote);
          saved = remote;
        }
        cache.setQueryData(["task", initial.id], saved);
        return saved;
      }),
  );
  const snapshot = useSyncExternalStore(session.subscribe, session.snapshot);
  useEffect(() => {
    if (snapshot.status === "saved")
      cache.setQueryData(["task", snapshot.task.id], snapshot.task);
  }, [cache, snapshot.status, snapshot.task]);
  const blocker = useBlocker(
    () => session.snapshot().status !== "saved" || extraGuard?.dirty === true,
  );
  const saveExtra = extraGuard?.save;
  useEffect(() => {
    if (blocker.state === "blocked") {
      void session
        .save()
        .then(() => saveExtra?.())
        .then(() => blocker.proceed())
        .catch(() => blocker.reset());
    }
  }, [blocker, session, saveExtra]);
  useEffect(() => {
    if (snapshot.status !== "unsaved") return;
    const timer = setTimeout(() => {
      void session.save().catch(() => {});
    }, 450);
    return () => clearTimeout(timer);
  }, [snapshot.status, snapshot.task.draft, session]);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (session.snapshot().status !== "saved" || extraGuard?.dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [session, extraGuard]);
  const replaceTask = useCallback(
    (saved: TaskRecord) => {
      if (saved.id !== initial.id || saved.project_id !== initial.project_id)
        throw new Error("加入回执不属于当前研究，当前草稿未改变");
      if (saved.revision < session.snapshot().task.revision) return;
      session.replace(saved);
      cache.setQueryData(["task", saved.id], saved);
    },
    [session, cache, initial.id, initial.project_id],
  );
  return { session, snapshot, task: snapshot.task, replaceTask };
}
export const saveMessage = (status: string) =>
  status === "saved"
    ? "已保存到服务器"
    : status === "saving"
      ? "正在保存…"
      : status === "conflict"
        ? "存在冲突，尚未保存"
        : status === "error"
          ? "保存失败，编辑仍保留"
          : "尚未保存";
