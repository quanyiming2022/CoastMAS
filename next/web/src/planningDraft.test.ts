import { expect, test } from "vitest";
import {
  PlanningDraftSession,
  PlanningConflict,
  type PlanningObject,
} from "./planningDraft";
const initial: PlanningObject = {
  id: "x",
  project_id: "p",
  kind: "objectives",
  name: "base",
  revision: 1,
  body: { mode: "single_objective", items: [] },
  versions: [],
};
test("autosave waits for acknowledgement and preserves edits arriving during the request", async () => {
  let finish!: (x: PlanningObject) => void;
  const sent: PlanningObject[] = [];
  const session = new PlanningDraftSession(initial, async (value) => {
    sent.push(value);
    if (sent.length === 1)
      return new Promise((resolve) => {
        finish = resolve;
      });
    return { ...value, revision: value.revision + 1 };
  });
  session.edit({ name: "first" });
  const pending = session.save();
  expect(session.snapshot().status).toBe("saving");
  session.edit({ name: "second" });
  finish({ ...sent[0]!, revision: 2 });
  await pending;
  expect(sent.map((x) => [x.name, x.revision])).toEqual([
    ["first", 1],
    ["second", 2],
  ]);
  expect(session.snapshot().value).toMatchObject({
    name: "second",
    revision: 3,
  });
  expect(session.snapshot().status).toBe("saved");
});
test("412 retains base, local and server for an explicit conflict decision", async () => {
  const remote = { ...initial, name: "server", revision: 2 };
  const session = new PlanningDraftSession(initial, async () => {
    throw new PlanningConflict(remote);
  });
  session.edit({ name: "mine" });
  await expect(session.save()).rejects.toThrow();
  expect(session.snapshot()).toMatchObject({
    status: "conflict",
    base: initial,
    value: { name: "mine" },
    remote,
  });
  session.useRemote();
  expect(session.snapshot().value).toEqual(remote);
});
test("network failure never claims saved and permits a retry", async () => {
  let attempt = 0;
  const session = new PlanningDraftSession(initial, async (value) => {
    if (!attempt++) throw new Error("offline");
    return { ...value, revision: 2 };
  });
  session.edit({ name: "local" });
  await expect(session.save()).rejects.toThrow("offline");
  expect(session.snapshot()).toMatchObject({
    status: "error",
    value: { name: "local" },
  });
  await session.save();
  expect(session.snapshot().status).toBe("saved");
});
