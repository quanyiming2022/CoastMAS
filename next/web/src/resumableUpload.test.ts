import { beforeEach, beforeAll, expect, test, vi } from "vitest";
import { webcrypto } from "node:crypto";
import { api } from "./api";
import {
  sha256,
  transfer,
  transferParts,
  type UploadSession,
} from "./resumableUpload";
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  api: vi.fn(),
}));
const session: UploadSession = {
  id: "session",
  name: "facts.csv",
  size: 12,
  chunk_size: 4,
  received_bytes: 4,
  status: "receiving",
  asset_id: null,
  error: null,
  parts: {},
};
beforeAll(() => {
  // jsdom Blob lacks arrayBuffer; use its own FileReader and Blob realm.
  Object.defineProperty(Blob.prototype, "arrayBuffer", {
    configurable: true,
    value: function () {
      return new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = () => reject(reader.error);
        reader.readAsArrayBuffer(this);
      });
    },
  });
});
beforeEach(() => {
  vi.mocked(api).mockReset();
  vi.stubGlobal("crypto", webcrypto);
});
test("verify every acknowledged part before appending bytes from a reselected file", async () => {
  const file = new File(["abcdefghijkl"], "facts.csv");
  const original = {
    ...session,
    parts: {
      "0": { sha256: await sha256(file.slice(0, 4)), size: 4 },
      "2": { sha256: "0".repeat(64), size: 4 },
    },
  };
  await expect(transfer(file, original, vi.fn())).rejects.toThrow(
    "内容与已保存分段不同",
  );
  expect(api).not.toHaveBeenCalled();
});
test("lost chunk and final acknowledgements recover through the server without repeating acceptance", async () => {
  const file = new File(["abcdefghijkl"], "facts.csv");
  const partial = {
    ...session,
    parts: { "0": { sha256: await sha256(file.slice(0, 4)), size: 4 } },
  };
  const all = {
    ...session,
    received_bytes: 12,
    parts: {
      ...partial.parts,
      "1": { sha256: await sha256(file.slice(4, 8)), size: 4 },
      "2": { sha256: await sha256(file.slice(8, 12)), size: 4 },
    },
  };
  const asset = { id: "actual-asset" };
  vi.mocked(api).mockImplementation(async (path) => {
    if (path.endsWith("/parts/1")) throw new Error("receipt lost");
    if (path.endsWith("/complete")) throw new Error("final receipt lost");
    if (path === "/assets/actual-asset") return asset;
    if (path === "/uploads/session") {
      const final = vi
        .mocked(api)
        .mock.calls.some(([p]) => p.endsWith("/complete"));
      return final ? { ...all, status: "ready", asset_id: asset.id } : all;
    }
    throw new Error("Unexpected request " + path);
  });
  expect(await transfer(file, partial, vi.fn())).toEqual(asset);
  expect(
    vi
      .mocked(api)
      .mock.calls.filter(([path]) => path.includes("/parts/"))
      .map(([path]) => path),
  ).toEqual(["/uploads/session/parts/1"]);
});
test("different file identity makes no network mutation", async () => {
  const file = new File(["abcdefghijkl"], "different.csv");
  await expect(transfer(file, session, vi.fn())).rejects.toThrow(
    "相同名称与大小",
  );
  expect(api).not.toHaveBeenCalled();
});

test("closing a local transfer never starts another chunk", async () => {
  const controller = new AbortController();
  controller.abort();
  const file = new File(["content"], "sample.csv");
  const session = {
    id: "closed",
    name: "sample.csv",
    size: 7,
    chunk_size: 4,
    received_bytes: 0,
    status: "receiving",
    asset_id: null,
    parts: {},
    error: null,
  };
  await expect(
    transferParts(file, session, () => {}, controller.signal),
  ).rejects.toMatchObject({ name: "AbortError" });
});
