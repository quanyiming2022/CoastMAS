import { expect, it } from "vitest";
import { OpinionSession, OpinionConflict } from "./opinionDraft";
const initial = { revision: 0, text: "", perspective: null };
it("saves typing during a pending request and only marks acknowledged text saved", async () => {
  let release: (v: {
    revision: number;
    text: string;
    perspective: null;
  }) => void = () => {};
  let calls = 0;
  const session = new OpinionSession(initial, async (value) => {
    calls++;
    if (calls === 1)
      return new Promise((resolve) => {
        release = resolve;
      });
    return { ...value, revision: value.revision + 1 };
  });
  session.edit({ text: "first" });
  const saving = session.save();
  session.edit({ text: "latest" });
  expect(session.snapshot().status).not.toBe("saved");
  release({ revision: 1, text: "first", perspective: null });
  await saving;
  expect(session.snapshot()).toMatchObject({
    status: "saved",
    value: { text: "latest", revision: 2 },
  });
});
it("keeps local and remote text on conflict, never silently overwrites", async () => {
  const session = new OpinionSession(initial, async () => {
    throw new OpinionConflict({
      revision: 1,
      text: "remote",
      perspective: null,
    });
  });
  session.edit({ text: "local" });
  await expect(session.save()).rejects.toThrow();
  expect(session.snapshot()).toMatchObject({
    status: "conflict",
    value: { text: "local" },
    remote: { text: "remote" },
  });
  session.useRemote();
  expect(session.snapshot()).toMatchObject({
    status: "saved",
    value: { text: "remote", revision: 1 },
  });
});
it("treats identical server content after lost acknowledgement as saved", async () => {
  const session = new OpinionSession(initial, async (value) => {
    throw new OpinionConflict({ ...value, revision: 1 });
  });
  session.edit({ text: "accepted remotely" });
  await session.save();
  expect(session.snapshot()).toMatchObject({
    status: "saved",
    value: { revision: 1 },
  });
});
