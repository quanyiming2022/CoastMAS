import { z } from "zod";
import { mergeDrafts, type Choice, type Conflict } from "./merge";
export const purposeSchema = z.enum([
  "inspect",
  "spatial",
  "entities",
  "temporal",
  "assessment",
  "optimization",
  "cluster",
  "regression",
  "workflow",
  "research",
  "comparison",
  "simulation",
]);
export const sourceSchema = z.object({
  asset_id: z.string(),
  revision: z.number(),
  layer: z.string().nullable().optional(),
});
export const bindingSchema = z.object({
  asset_id: z.string(),
  field: z.string(),
  unit: z.string().nullable(),
  concept: z.string().nullable(),
  support: z.string().nullable(),
  template_id: z.string().nullable(),
  template_revision: z.number().nullable().optional(),
  role: z.enum([
    "feature",
    "response",
    "identity",
    "time",
    "geometry",
    "constraint",
    "ignored",
  ]),
});
export const draftSchema = z.object({
  title: z.string(),
  purpose: purposeSchema,
  selection: z.array(sourceSchema),
  mapping: z.array(bindingSchema),
  options: z.record(z.string(), z.json()),
  method_id: z.string().nullable().optional(),
});
export const taskSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  revision: z.number(),
  updated: z.number(),
  draft: draftSchema,
});
export type Draft = z.infer<typeof draftSchema>;
export type TaskRecord = z.infer<typeof taskSchema>;
export type Save = (draft: Draft, revision: number) => Promise<TaskRecord>;
export class RemoteDraftConflict extends Error {
  constructor(public remote: TaskRecord) {
    super("远端草稿已有新版本");
  }
}
type Snapshot = {
  task: TaskRecord;
  status: "saved" | "unsaved" | "saving" | "error" | "conflict";
  error: string | null;
  conflicts: Conflict[];
};
export class DraftSession {
  private current: Snapshot;
  private saved: string;
  private listeners = new Set<() => void>();
  private pending: Promise<void> | null = null;
  private remote: TaskRecord | null = null;
  constructor(
    task: TaskRecord,
    private persist: Save,
  ) {
    this.current = {
      task: structuredClone(task),
      status: "saved",
      error: null,
      conflicts: [],
    };
    this.saved = JSON.stringify(task.draft);
  }
  snapshot = () => this.current;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
  private emit() {
    for (const listener of this.listeners) listener();
  }
  edit(change: (draft: Draft) => Draft) {
    const draft = change(structuredClone(this.current.task.draft));
    if (this.remote) {
      const merged = mergeDrafts(
        JSON.parse(this.saved),
        draft,
        this.remote.draft,
      );
      if (merged.conflicts.length) {
        this.current = {
          ...this.current,
          task: { ...this.current.task, draft },
          conflicts: merged.conflicts,
        };
      } else {
        this.saved = JSON.stringify(this.remote.draft);
        this.current = {
          task: { ...this.remote, draft: draftSchema.parse(merged.draft) },
          status:
            this.saved === JSON.stringify(merged.draft) ? "saved" : "unsaved",
          error: null,
          conflicts: [],
        };
        this.remote = null;
      }
    } else {
      this.current = {
        task: { ...this.current.task, draft },
        status: "unsaved",
        error: null,
        conflicts: [],
      };
    }
    this.emit();
  }
  replace(task: TaskRecord) {
    if (this.pending) throw new Error("保存尚未完成");
    this.remote = null;
    this.current = { task, status: "saved", error: null, conflicts: [] };
    this.saved = JSON.stringify(task.draft);
    this.emit();
  }
  resolve(choices: Record<string, Choice>) {
    if (!this.remote) throw new Error("没有待处理的冲突");
    const result = mergeDrafts(
      JSON.parse(this.saved),
      this.current.task.draft,
      this.remote.draft,
      choices,
    );
    if (result.conflicts.length) throw new Error("请为每项冲突选择采用的版本");
    const draft = draftSchema.parse(result.draft);
    this.saved = JSON.stringify(this.remote.draft);
    this.current = {
      task: { ...this.remote, draft },
      status: this.saved === JSON.stringify(draft) ? "saved" : "unsaved",
      error: null,
      conflicts: [],
    };
    this.remote = null;
    this.emit();
  }
  save(): Promise<void> {
    if (this.current.status === "conflict")
      return Promise.reject(new Error("请先处理同一信息的并发冲突"));
    if (this.pending) return this.pending;
    this.pending = this.flush().finally(() => {
      this.pending = null;
    });
    return this.pending;
  }
  private async flush() {
    let reconciliations = 0;
    while (JSON.stringify(this.current.task.draft) !== this.saved) {
      const sent = structuredClone(this.current.task.draft),
        revision = this.current.task.revision;
      this.current = { ...this.current, status: "saving", error: null };
      this.emit();
      try {
        const server = await this.persist(sent, revision);
        this.saved = JSON.stringify(server.draft);
        const modified =
          JSON.stringify(this.current.task.draft) !== JSON.stringify(sent);
        this.current = {
          task: {
            ...server,
            draft: modified ? this.current.task.draft : server.draft,
          },
          status: modified ? "unsaved" : "saved",
          error: null,
          conflicts: [],
        };
        this.emit();
      } catch (error) {
        if (
          error instanceof RemoteDraftConflict &&
          error.remote.id === this.current.task.id &&
          error.remote.project_id === this.current.task.project_id
        ) {
          const merged = mergeDrafts(
            JSON.parse(this.saved),
            this.current.task.draft,
            error.remote.draft,
          );
          if (merged.conflicts.length) {
            this.remote = error.remote;
            this.current = {
              ...this.current,
              status: "conflict",
              error: "同一信息存在两份修改，请选择需要保留的版本",
              conflicts: merged.conflicts,
            };
            this.emit();
            throw error;
          }
          if (reconciliations++ < 2) {
            this.saved = JSON.stringify(error.remote.draft);
            const draft = draftSchema.parse(merged.draft);
            this.current = {
              task: { ...error.remote, draft },
              status:
                this.saved === JSON.stringify(draft) ? "saved" : "unsaved",
              error: null,
              conflicts: [],
            };
            this.emit();
            continue;
          }
        }
        this.current = {
          ...this.current,
          status: "error",
          error:
            error instanceof Error ? error.message : "保存失败，编辑内容已保留",
        };
        this.emit();
        throw error;
      }
    }
  }
}
