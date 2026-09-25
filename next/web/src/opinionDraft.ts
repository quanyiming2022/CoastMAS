export type Opinion = {
  revision: number;
  text: string;
  perspective: string | null;
};
type Snapshot = {
  value: Opinion;
  status: "saved" | "unsaved" | "saving" | "error" | "conflict";
  error: unknown;
  remote: Opinion | null;
};
export class OpinionConflict extends Error {
  constructor(public remote: Opinion) {
    super("另一窗口已更新意见，请核对。");
  }
}
const equal = (a: Opinion, b: Opinion) =>
  a.text === b.text && a.perspective === b.perspective;
export class OpinionSession {
  private state: Snapshot;
  private listeners = new Set<() => void>();
  private pending: Promise<void> | null = null;
  constructor(
    initial: Opinion,
    private persist: (value: Opinion) => Promise<Opinion>,
  ) {
    this.state = { value: initial, status: "saved", error: null, remote: null };
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
  edit(change: Partial<Pick<Opinion, "text" | "perspective">>) {
    this.state = {
      ...this.state,
      value: { ...this.state.value, ...change },
      status: this.state.remote ? "conflict" : "unsaved",
    };
    this.emit();
  }
  replace(value: Opinion) {
    this.state = { value, status: "saved", error: null, remote: null };
    this.emit();
  }
  useRemote() {
    if (this.state.remote) this.replace(this.state.remote);
  }
  keepLocal() {
    if (this.state.remote) {
      this.state = {
        ...this.state,
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
      return Promise.reject(new OpinionConflict(this.state.remote));
    this.pending = this.flush().finally(() => {
      this.pending = null;
    });
    return this.pending;
  };
  private async flush() {
    while (this.state.status !== "saved") {
      const sent = { ...this.state.value };
      this.state = { ...this.state, status: "saving", error: null };
      this.emit();
      let saved: Opinion;
      try {
        saved = await this.persist(sent);
      } catch (error) {
        if (error instanceof OpinionConflict && equal(sent, error.remote)) {
          saved = error.remote;
        } else {
          this.state = {
            ...this.state,
            status: error instanceof OpinionConflict ? "conflict" : "error",
            error,
            remote: error instanceof OpinionConflict ? error.remote : null,
          };
          this.emit();
          throw error;
        }
      }
      const unchanged = equal(this.state.value, sent);
      this.state = {
        value: unchanged
          ? saved
          : { ...this.state.value, revision: saved.revision },
        status: unchanged ? "saved" : "unsaved",
        error: null,
        remote: null,
      };
      this.emit();
    }
  }
}
