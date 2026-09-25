import { z } from "zod";
import { api, APIError, assetSchema } from "./api";
import { taskSchema, type TaskRecord } from "./draft";

const receiptSchema = z.object({
  task: taskSchema,
  intent: z.string(),
  items: z.array(
    z.object({
      asset_id: z.string(),
      revision: z.number(),
      status: z.enum(["added", "already_present", "rejected"]),
      code: z.string().optional(),
      message: z.string().optional(),
    }),
  ),
});
export type AttachmentReceipt = z.infer<typeof receiptSchema>;
type AttachBody = {
  expected_revision: number;
  idempotency_key: string;
  inputs: { asset_id: string; revision: number }[];
};
export function acceptsAttachment(
  current: TaskRecord | undefined,
  receipt: AttachmentReceipt,
) {
  return (
    current?.id === receipt.task.id &&
    current.project_id === receipt.task.project_id &&
    current.revision <= receipt.task.revision
  );
}

/** Keep an uncertain request unchanged until acknowledged or explicitly rejected. */
export class InputAttachmentClient {
  private requests = new Map<string, AttachBody>();
  private pending = new Map<string, Promise<AttachmentReceipt>>();
  constructor(
    private send = (taskId: string, body: AttachBody) =>
      api(`/tasks/${taskId}/inputs:attach`, receiptSchema, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  ) {}
  attach(task: TaskRecord, asset: { id: string; revision: number }) {
    const key = `${task.id}:${asset.id}`;
    const running = this.pending.get(key);
    if (running) return running;
    const body = this.requests.get(key) ?? {
      expected_revision: task.revision,
      idempotency_key: crypto.randomUUID(),
      inputs: [{ asset_id: asset.id, revision: asset.revision }],
    };
    this.requests.set(key, body);
    const promise = this.send(task.id, body)
      .then((receipt) => {
        this.requests.delete(key);
        return receipt;
      })
      .catch((error: unknown) => {
        if (error instanceof APIError) this.requests.delete(key);
        throw error;
      })
      .finally(() => this.pending.delete(key));
    this.pending.set(key, promise);
    return promise;
  }
  async attachId(task: TaskRecord, assetId: string) {
    const asset = await api(`/assets/${assetId}`, assetSchema);
    return this.attach(task, asset);
  }
}
