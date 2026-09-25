import { describe, it, expect } from "vitest";
import { mergeDrafts } from "./merge";
import { DraftSession, RemoteDraftConflict, type TaskRecord } from "./draft";
const task: TaskRecord = {
  id: "one",
  project_id: "project",
  revision: 1,
  updated: 1,
  draft: {
    title: "base",
    purpose: "inspect",
    selection: [],
    mapping: [],
    options: { seed: 1, standardize: true },
    method_id: null,
  },
};
describe("concurrent draft reconciliation", () => {
  it("merges disjoint edits and retains false and zero", () => {
    const result = mergeDrafts(
      task.draft,
      { ...task.draft, title: "mine" },
      { ...task.draft, options: { seed: 0, standardize: false } },
    );
    expect(result.conflicts).toEqual([]);
    expect(result.draft.title).toBe("mine");
    expect(result.draft.options).toEqual({ seed: 0, standardize: false });
  });
  it("requires explicit choice for the same changed field", () => {
    const remote = { ...task.draft, title: "theirs" },
      local = { ...task.draft, title: "mine" };
    const result = mergeDrafts(task.draft, local, remote);
    expect(result.conflicts.map((c) => c.path)).toEqual(["/title"]);
    expect(
      mergeDrafts(task.draft, local, remote, { "/title": "remote" }).draft
        .title,
    ).toBe("theirs");
    expect(
      mergeDrafts(task.draft, local, remote, { "/title": "local" }).draft.title,
    ).toBe("mine");
  });
  it("does not combine reordered scientific rows by position", () => {
    const base = { ...task.draft, options: { coefficients: [1, 2] } };
    expect(
      mergeDrafts(
        base,
        { ...base, options: { coefficients: [2, 1] } },
        { ...base, options: { coefficients: [1, 3] } },
      ).conflicts[0]?.path,
    ).toBe("/options");
  });
  it("automatically retries disjoint conflicts against the new server revision", async () => {
    const revisions: number[] = [];
    const session = new DraftSession(task, async (draft, revision) => {
      revisions.push(revision);
      if (revision === 1)
        throw new RemoteDraftConflict({
          ...task,
          revision: 2,
          draft: { ...task.draft, options: { seed: 0, standardize: false } },
        });
      return { ...task, revision: revision + 1, draft };
    });
    session.edit((d) => ({ ...d, title: "my title" }));
    await session.save();
    expect(revisions).toEqual([1, 2]);
    expect(session.snapshot().task.draft).toMatchObject({
      title: "my title",
      options: { seed: 0, standardize: false },
    });
    expect(session.snapshot().status).toBe("saved");
  });
  it("keeps both conflicting values until resolved and server-acknowledged", async () => {
    const session = new DraftSession(task, async (draft, revision) => {
      if (revision === 1)
        throw new RemoteDraftConflict({
          ...task,
          revision: 2,
          draft: { ...task.draft, title: "other" },
        });
      return { ...task, revision: revision + 1, draft };
    });
    session.edit((d) => ({ ...d, title: "mine" }));
    await expect(session.save()).rejects.toThrow();
    expect(session.snapshot().status).toBe("conflict");
    expect(session.snapshot().conflicts[0]).toMatchObject({
      local: "mine",
      remote: "other",
    });
    session.resolve({ "/title": "local" });
    expect(session.snapshot().status).toBe("unsaved");
    await session.save();
    expect(session.snapshot().task.draft.title).toBe("mine");
    expect(session.snapshot().task.revision).toBe(3);
  });
});
