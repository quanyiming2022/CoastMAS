import { z } from "zod";
import { api, assetSchema, type Asset } from "./api";
import {
  uploadSchema,
  transferParts,
  type UploadSession,
} from "./resumableUpload";
export const groupSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  asset_id: z.string().nullable(),
  members: z.array(
    z.object({
      upload_id: z.string(),
      relative_path: z.string(),
      upload: uploadSchema,
    }),
  ),
});
export type UploadGroup = z.infer<typeof groupSchema>;
export const relativeName = (file: File) =>
  file.webkitRelativePath || file.name;
export const isSidecar = (name: string) =>
  /\.(tfw|tifw|tiffw|wld|aux\.xml|ovr|msk|shx|dbf|prj|cpg|qix|sbn|sbx)$/i.test(
    name,
  );
export function groupFiles(files: File[]) {
  const remaining = new Set(files),
    groups: File[][] = [];
  for (const file of files) {
    const path = relativeName(file);
    if (/\.shp$/i.test(path)) {
      const stem = path.slice(0, -4).toLowerCase();
      const members = files.filter(
        (candidate) =>
          relativeName(candidate).slice(0, -4).toLowerCase() === stem &&
          /\.(shp|shx|dbf|prj|cpg|qix|sbn|sbx)$/i.test(relativeName(candidate)),
      );
      groups.push(members);
      members.forEach((m) => remaining.delete(m));
      continue;
    }
    if (!/\.tiff?$/i.test(path)) continue;
    const stem = path.replace(/\.tiff?$/i, "");
    const names = new Set(
      [
        path,
        path + ".aux.xml",
        path + ".ovr",
        path + ".msk",
        path + "w",
        stem + ".tfw",
        stem + ".wld",
      ].map((s) => s.toLowerCase()),
    );
    const members = files.filter((candidate) =>
      names.has(relativeName(candidate).toLowerCase()),
    );
    groups.push(members);
    members.forEach((member) => remaining.delete(member));
  }
  remaining.forEach((file) => groups.push([file]));
  return groups;
}
export async function uploadGroup(
  project: string,
  files: File[],
  progress: (state: UploadSession) => void,
  resume?: UploadGroup,
  signal?: AbortSignal,
  received?: (kind: "upload" | "group" | "source", id: string) => Promise<void>,
): Promise<Asset> {
  signal?.throwIfAborted();
  let group =
    resume ??
    (await api(`/projects/${project}/upload-groups`, groupSchema, {
      method: "POST",
      body: JSON.stringify({
        idempotency_key: crypto.randomUUID(),
        files: files.map((file) => ({
          relative_path: relativeName(file),
          size: file.size,
        })),
      }),
    }));
  await received?.("group", group.id);
  const added = files.filter(
    (file) =>
      !group.members.some(
        (member) => member.relative_path === relativeName(file),
      ),
  );
  if (added.length)
    group = await api(`/upload-groups/${group.id}/members`, groupSchema, {
      method: "POST",
      body: JSON.stringify({
        idempotency_key: crypto.randomUUID(),
        files: added.map((file) => ({
          relative_path: relativeName(file),
          size: file.size,
        })),
      }),
    });
  for (const member of group.members) {
    const file = files.find(
      (file) => relativeName(file) === member.relative_path,
    );
    if (file) await transferParts(file, member.upload, progress, signal);
    else if (member.upload.received_bytes !== member.upload.size)
      throw new Error(`请补选未传完的原件：${member.relative_path}`);
  }
  return (
    await api(
      `/upload-groups/${group.id}/complete`,
      z.object({ asset: assetSchema }),
      { method: "POST" },
    )
  ).asset;
}
