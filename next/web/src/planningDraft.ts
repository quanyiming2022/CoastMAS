import { z } from "zod";
export const planningItemSchema = z.object({
  metric: z.string().optional(),
  weight: z.number().optional(),
  recipe: z.string().optional(),
  limit: z.number().optional(),
  unit: z.string().optional(),
  basis: z.string().optional(),
});
export const planningBodySchema = z.object({
  mode: z
    .enum([
      "single_objective",
      "weighted_multiobjective",
      "pareto_multiobjective",
    ])
    .optional(),
  items: z.array(planningItemSchema).optional(),
  template: z.string().optional(),
  actions: z.array(z.string()).optional(),
});
export const planningObjectSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  kind: z.enum(["objectives", "constraints", "decisions"]),
  name: z.string(),
  revision: z.number(),
  body: planningBodySchema,
  versions: z.array(
    z.object({
      id: z.string(),
      version: z.number(),
      name: z.string(),
      sha256: z.string(),
      draft_revision: z.number(),
    }),
  ),
});
export type PlanningObject = z.infer<typeof planningObjectSchema>;
export type PlanningBody = z.infer<typeof planningBodySchema>;
export type PlanningKind = PlanningObject["kind"];
type State = {
  value: PlanningObject;
  base: PlanningObject;
  status: "saved" | "unsaved" | "saving" | "error" | "conflict";
  error: unknown;
  remote: PlanningObject | null;
};
export class PlanningConflict extends Error {
  constructor(public remote: PlanningObject) {
    super("其他成员已更新，请比较后继续");
  }
}
const same = (a: PlanningObject, b: PlanningObject) =>
  a.name === b.name && JSON.stringify(a.body) === JSON.stringify(b.body);
export class PlanningDraftSession {
  private state: State;
  private listeners = new Set<() => void>();
  private pending: Promise<void> | null = null;
  constructor(
    initial: PlanningObject,
    private persist: (value: PlanningObject) => Promise<PlanningObject>,
  ) {
    this.state = {
      value: initial,
      base: initial,
      status: "saved",
      error: null,
      remote: null,
    };
  }
  snapshot = () => this.state;
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  private emit() {
    for (const fn of this.listeners) fn();
  }
  edit(change: Partial<Pick<PlanningObject, "name" | "body">>) {
    this.state = {
      ...this.state,
      value: { ...this.state.value, ...change },
      status: this.state.remote ? "conflict" : "unsaved",
    };
    this.emit();
  }
  replace(value: PlanningObject) {
    this.state = {
      value,
      base: value,
      status: "saved",
      error: null,
      remote: null,
    };
    this.emit();
  }
  useRemote() {
    if (this.state.remote) this.replace(this.state.remote);
  }
  keepLocal() {
    if (this.state.remote) {
      this.state = {
        ...this.state,
        base: this.state.remote,
        value: { ...this.state.value, revision: this.state.remote.revision },
        remote: null,
        error: null,
        status: "unsaved",
      };
      this.emit();
    }
  }
  save = (): Promise<void> => {
    if (this.pending) return this.pending;
    if (this.state.status === "saved") return Promise.resolve();
    if (this.state.remote)
      return Promise.reject(new PlanningConflict(this.state.remote));
    this.pending = this.flush().finally(() => {
      this.pending = null;
    });
    return this.pending;
  };
  private async flush() {
    while (this.state.status !== "saved") {
      const sent = this.state.value;
      this.state = { ...this.state, status: "saving", error: null };
      this.emit();
      try {
        const saved = await this.persist(sent),
          unchanged = same(sent, this.state.value);
        this.state = {
          value: unchanged
            ? saved
            : {
                ...this.state.value,
                revision: saved.revision,
                versions: saved.versions,
              },
          base: saved,
          status: unchanged ? "saved" : "unsaved",
          error: null,
          remote: null,
        };
        this.emit();
      } catch (error) {
        this.state = {
          ...this.state,
          error,
          status: error instanceof PlanningConflict ? "conflict" : "error",
          remote: error instanceof PlanningConflict ? error.remote : null,
        };
        this.emit();
        throw error;
      }
    }
  }
}
