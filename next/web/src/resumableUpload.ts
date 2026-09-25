import { z } from "zod";
import { api, assetSchema, type Asset } from "./api";
export const uploadSchema = z.object({
  id: z.string(),
  name: z.string(),
  size: z.number(),
  chunk_size: z.number(),
  received_bytes: z.number(),
  status: z.string(),
  asset_id: z.string().nullable(),
  parts: z.record(
    z.string(),
    z.object({ sha256: z.string(), size: z.number() }),
  ),
  error: z.object({ code: z.string(), message: z.string() }).nullable(),
});
export type UploadSession = z.infer<typeof uploadSchema>;
export async function sha256(blob: Blob) {
  const bytes = await blob.arrayBuffer();
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash), (v) =>
    v.toString(16).padStart(2, "0"),
  ).join("");
}
export async function finishUpload(session: UploadSession): Promise<Asset> {
  try {
    return (
      await api(
        `/uploads/${session.id}/complete`,
        z.object({ asset: assetSchema }),
        { method: "POST" },
      )
    ).asset;
  } catch (error) {
    const state = await api(`/uploads/${session.id}`, uploadSchema);
    if (state.status === "ready" && state.asset_id)
      return api(`/assets/${state.asset_id}`, assetSchema);
    throw error;
  }
}
export async function transferParts(
  file: File,
  session: UploadSession,
  progress: (state: UploadSession) => void,
  signal?: AbortSignal,
) {
  if (file.name !== session.name || file.size !== session.size)
    throw new Error("请重选相同名称与大小的原文件；新文件请使用导入入口。");
  // Verify ALL acknowledged content before adding anything to a resumed stream.
  for (const [index, part] of Object.entries(session.parts)) {
    signal?.throwIfAborted();
    const start = Number(index) * session.chunk_size;
    if ((await sha256(file.slice(start, start + part.size))) !== part.sha256)
      throw new Error(
        "重选文件内容与已保存分段不同，原上传未修改。请重选原文件或新建接入。",
      );
  }
  let state = session;
  const count = Math.ceil(file.size / session.chunk_size);
  for (let index = 0; index < count; index++) {
    signal?.throwIfAborted();
    if (state.parts[String(index)]) continue;
    const blob = file.slice(
      index * state.chunk_size,
      Math.min(file.size, (index + 1) * state.chunk_size),
    );
    const hash = await sha256(blob),
      form = new FormData();
    form.append("file", blob, "part");
    form.append("sha256", hash);
    try {
      state = await api(`/uploads/${state.id}/parts/${index}`, uploadSchema, {
        method: "POST",
        body: form,
        signal,
      });
    } catch (error) {
      signal?.throwIfAborted();
      const restored = await api(`/uploads/${state.id}`, uploadSchema);
      if (restored.parts[String(index)]?.sha256 !== hash) throw error;
      state = restored;
    }
    progress(state);
  }
  return state;
}
export async function transfer(
  file: File,
  session: UploadSession,
  progress: (state: UploadSession) => void,
  signal?: AbortSignal,
) {
  return finishUpload(await transferParts(file, session, progress, signal));
}
