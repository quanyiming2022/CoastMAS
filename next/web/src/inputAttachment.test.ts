import { test, expect } from "vitest";
import {
  acceptsAttachment,
  InputAttachmentClient,
  type AttachmentReceipt,
} from "./inputAttachment";
import { taskSchema } from "./draft";
const task = taskSchema.parse({
  id: "a",
  project_id: "p",
  revision: 1,
  updated: 1,
  draft: {
    title: "A",
    purpose: "assessment",
    selection: [],
    mapping: [],
    options: {},
  },
});
const receipt: AttachmentReceipt = {
  task: { ...task, revision: 2 },
  intent: "test",
  items: [{ asset_id: "x", revision: 1, status: "added" }],
};
test("lost response retries the identical intent and payload, including its frozen revision", async () => {
  const bodies: unknown[] = [];
  const client = new InputAttachmentClient(async (_id, body) => {
    bodies.push(body);
    if (bodies.length === 1) throw new TypeError("network");
    return receipt;
  });
  await expect(client.attach(task, { id: "x", revision: 1 })).rejects.toThrow(
    "network",
  );
  await client.attach({ ...task, revision: 9 }, { id: "x", revision: 2 });
  expect(bodies[1]).toEqual(bodies[0]);
});
test("double click shares one in-flight transaction", async () => {
  let calls = 0;
  const client = new InputAttachmentClient(async () => {
    calls++;
    return receipt;
  });
  const first = client.attach(task, { id: "x", revision: 1 });
  expect(client.attach(task, { id: "x", revision: 1 })).toBe(first);
  await first;
  expect(calls).toBe(1);
});
test("a late receipt cannot replace a different task or a newer draft", () => {
  expect(acceptsAttachment({ ...task, id: "b" }, receipt)).toBe(false);
  expect(acceptsAttachment({ ...task, revision: 3 }, receipt)).toBe(false);
  expect(acceptsAttachment(task, receipt)).toBe(true);
});
