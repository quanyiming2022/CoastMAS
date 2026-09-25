import { z } from "zod";
let csrf = "";
export const setCSRF = (value: string) => {
  csrf = value;
};
export class APIError extends Error {
  constructor(
    public status: number,
    message: string,
    public details: unknown,
    public code?: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (options.method && options.method !== "GET")
    headers.set("X-CSRF-Token", csrf);
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  const data: unknown = await response.json();
  if (!response.ok) {
    const issue = z
      .object({
        message: z.string().optional(),
        code: z.string().optional(),
        detail: z.unknown().optional(),
        details: z.unknown().optional(),
      })
      .passthrough()
      .safeParse(data);
    throw new APIError(
      response.status,
      issue.success
        ? (issue.data.message ?? "请求校验失败，请检查输入")
        : "服务请求失败",
      issue.success ? issue.data.details : data,
      issue.success ? issue.data.code : undefined,
    );
  }
  return schema.parse(data);
}
export const actorSchema = z.object({
  id: z.string(),
  email: z.string(),
  system_admin: z.boolean(),
  csrf: z.string(),
});
export const projectSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
});
export const fieldSchema = z
  .object({
    name: z.string(),
    data_type: z.string(),
    unit: z.string().nullable(),
    concept: z.string().nullable(),
  })
  .passthrough();
export const layerSchema = z
  .object({
    name: z.string(),
    fields: z.array(fieldSchema),
    preview: z.json(),
    row_count: z.number().nullable(),
  })
  .passthrough();
export const temporalCandidateSchema = z.object({
  variable: z.string(),
  axis: z.string(),
  method: z.string().nullable(),
  cell_method: z.string(),
  unit: z.string().nullable(),
  calendar: z.string(),
  time_axis_unit: z.string(),
});
export const assetSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  revision: z.number(),
  name: z.string(),
  sha256: z.string(),
  size: z.number(),
  facts: z
    .object({
      profile: z.string(),
      standard_version: z.string().nullable(),
      layers: z.array(layerSchema),
      issues: z.array(z.json()),
      temporal_candidates: z.array(temporalCandidateSchema).optional(),
    })
    .passthrough(),
});
export type Asset = z.infer<typeof assetSchema>;
export const jobSchema = z
  .object({
    id: z.string(),
    task_id: z.string(),
    status: z.string(),
    error: z
      .object({ code: z.string(), message: z.string() })
      .passthrough()
      .nullable()
      .optional(),
  })
  .passthrough();
export const resultSchema = z.object({
  data: z.record(z.string(), z.json()),
  states: z.record(z.string(), z.json()),
  manifest: z.record(z.string(), z.json()),
});

export const templateSchema = z.object({
  id: z.string(),
  revision: z.number(),
  approved: z.boolean(),
  spec: z.object({
    title: z.string(),
    purpose: z.string(),
    basis: z.string(),
    profiles: z.array(z.string()),
    configuration: z.record(z.string(), z.json()),
  }),
});
