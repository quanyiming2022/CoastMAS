import { describe, expect, it } from "vitest";
import { DraftSession, type TaskRecord } from "./draft";
const task: TaskRecord = {
  id: "task",
  project_id: "project",
  revision: 1,
  updated: 1,
  draft: {
    title: "Original",
    purpose: "inspect",
    selection: [],
    mapping: [],
    options: {},
    method_id: null,
  },
};
describe("server-acknowledged task draft", () => {
  it("does not claim saved before the server reply", async () => {
    let release!: (value: TaskRecord) => void;
    const session = new DraftSession(
      task,
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    session.edit((d) => ({ ...d, title: "Edited" }));
    expect(session.snapshot().status).toBe("unsaved");
    const pending = session.save();
    expect(session.snapshot().status).toBe("saving");
    release({
      ...task,
      revision: 2,
      updated: 2,
      draft: { ...task.draft, title: "Edited" },
    });
    await pending;
    expect(session.snapshot().status).toBe("saved");
    expect(session.snapshot().task.revision).toBe(2);
  });
  it("serializes edits made during a save instead of losing them", async () => {
    let release!: (value: TaskRecord) => void;
    const revisions: number[] = [];
    const session = new DraftSession(task, async (draft, expected) => {
      revisions.push(expected);
      if (expected === 1)
        return new Promise((resolve) => {
          release = resolve;
        });
      return { ...task, revision: expected + 1, draft, updated: 3 };
    });
    session.edit((d) => ({ ...d, title: "First" }));
    const pending = session.save();
    session.edit((d) => ({ ...d, title: "Second" }));
    release({ ...task, revision: 2, draft: { ...task.draft, title: "First" } });
    await pending;
    expect(revisions).toEqual([1, 2]);
    expect(session.snapshot().task.draft.title).toBe("Second");
    expect(session.snapshot().status).toBe("saved");
  });
  it("retains edits after a server conflict without overwriting remotely", async () => {
    const session = new DraftSession(task, async () => {
      throw new Error("DRAFT_CONFLICT");
    });
    session.edit((d) => ({ ...d, title: "My work" }));
    await expect(session.save()).rejects.toThrow("DRAFT_CONFLICT");
    expect(session.snapshot().status).toBe("error");
    expect(session.snapshot().task.draft.title).toBe("My work");
    expect(session.snapshot().task.revision).toBe(1);
  });
});
