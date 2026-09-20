import { z } from "zod";

export const SESSION_EXPIRED = "coastmas:session-expired";

export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status = 0,
    public readonly requestId?: string,
    public readonly details?: unknown,
  ) {
    super(message);
  }
}
const errorSchema = z.object({
  error_code: z.string(),
  message: z.string(),
  request_id: z.string().optional(),
  details: z.unknown().optional(),
});
export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  idempotencyKey?: string;
}
export async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  options: RequestOptions = {},
): Promise<T> {
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("\\"))
    throw new ApiError("INVALID_PATH", "无效的接口地址");
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  if (method !== "GET") {
    const csrf = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("coastmas_csrf="))
      ?.slice("coastmas_csrf=".length);
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  if (options.idempotencyKey)
    headers.set("Idempotency-Key", options.idempotencyKey);
  let response: Response;
  try {
    response = await fetch("/api/v1" + path, {
      method,
      headers,
      credentials: "same-origin",
      signal: options.signal,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError("NETWORK_ERROR", "无法连接服务，请检查连接后重试");
  }
  if (
    response.status === 401 &&
    path !== "/auth/me" &&
    path !== "/auth/login"
  ) {
    window.dispatchEvent(new Event(SESSION_EXPIRED));
  }
  let value: unknown;
  try {
    value = response.status === 204 ? null : await response.json();
  } catch {
    throw new ApiError(
      "HTTP_" + response.status,
      "服务返回了无法解析的数据",
      response.status,
    );
  }
  if (!response.ok) {
    const parsed = errorSchema.safeParse(value);
    if (!parsed.success)
      throw new ApiError(
        "HTTP_" + response.status,
        "请求失败",
        response.status,
      );
    throw new ApiError(
      parsed.data.error_code,
      parsed.data.message,
      response.status,
      parsed.data.request_id,
      parsed.data.details,
    );
  }
  const parsed = schema.safeParse(value);
  if (!parsed.success)
    throw new ApiError(
      "RESPONSE_CONTRACT",
      "响应不符合数据契约，请联系管理员",
      response.status,
      response.headers.get("X-Request-ID") ?? undefined,
    );
  return parsed.data;
}
export const userSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  is_admin: z.boolean(),
});
export const projectSchema = z.object({
  id: z.string(),
  name: z.string(),
  owner_id: z.string(),
});
export const resourceSchema = z.object({
  id: z.string(),
  name: z.string(),
  version: z.number().int().positive(),
  enabled: z.boolean(),
  published: z.boolean(),
  summary: z.record(z.string(), z.unknown()),
});
export type ResourceSummary = z.infer<typeof resourceSchema>;
export const revisionSchema = z.object({
  resource_id: z.string(),
  version: z.number().int().positive(),
  checksum: z.string(),
  spec: z.record(z.string(), z.unknown()),
});
export const dashboardSchema = z.object({
  counts: z.record(z.string(), z.number().int().nonnegative()),
  run_states: z.record(z.string(), z.number().int().nonnegative()),
  provider_configured: z.boolean(),
  recent_runs: z.array(
    z.object({
      id: z.string(),
      status: z.string(),
      progress: z.number(),
      created_at: z.string(),
    }),
  ),
});
export const jobSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  submitted_by: z.string(),
  status: z.enum(["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]),
  cancel_requested: z.boolean(),
  progress: z.number(),
  attempt: z.number(),
  manifest: z.record(z.string(), z.unknown()),
  error: z.record(z.string(), z.unknown()).nullable(),
});
export const resultSchema = z.object({
  id: z.string(),
  job_id: z.string(),
  checksum: z.string(),
  created_at: z.string(),
});
