import { z } from "zod";
import { useState } from "react";
import { APIError } from "./api";
import { purposeSchema } from "./draft";
export const purposes: Record<z.infer<typeof purposeSchema>, string> = {
  inspect: "资料检查",
  spatial: "空间处理",
  entities: "地理实体",
  temporal: "时间适配",
  assessment: "综合评价",
  optimization: "空间优化",
  cluster: "投影寻踪聚类",
  regression: "投影寻踪回归",
  workflow: "组合工作流",
  research: "科研验证",
  comparison: "成果比较",
  simulation: "模拟",
};
function diagnostic(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(diagnostic);
  if (value !== null && typeof value === "object") {
    const entry = value as Record<string, unknown>;
    const sensitiveLocation =
      Array.isArray(entry.loc) &&
      entry.loc.some((part) =>
        /password|secret|token|cookie|authorization/i.test(String(part)),
      );
    return Object.fromEntries(
      Object.entries(entry).map(([key, item]) => [
        key,
        /password|secret|token|cookie|authorization/i.test(key) ||
        (key === "input" && sensitiveLocation)
          ? "[已隐藏]"
          : diagnostic(item),
      ]),
    );
  }
  return value;
}
export function ErrorNotice({ error }: { error: unknown }) {
  const [copied, setCopied] = useState(false),
    [copyError, setCopyError] = useState(false);
  if (!error) return null;
  const summary =
    error instanceof TypeError &&
    /fetch|network|load failed/i.test(error.message)
      ? "连接失败，请检查网络后重试"
      : error instanceof z.ZodError
        ? "服务返回的信息不完整，请重试"
        : error instanceof Error
          ? error.message
          : String(error);
  const code = error instanceof APIError ? error.code : undefined;
  const details =
    error instanceof APIError
      ? diagnostic(error.details)
      : summary !== (error instanceof Error ? error.message : String(error))
        ? String(error)
        : undefined;
  return (
    <div className="error-notice">
      <p role="alert" className="error">
        {summary}
      </p>
      {code || details ? (
        <details>
          <summary>错误详情</summary>
          {code ? (
            <p>
              <code>{code}</code>{" "}
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  void navigator.clipboard.writeText(code).then(
                    () => {
                      setCopied(true);
                      setCopyError(false);
                    },
                    () => setCopyError(true),
                  );
                }}
              >
                {copied ? "已复制" : "复制错误码"}
              </button>
            </p>
          ) : null}
          {details ? (
            <pre>
              {typeof details === "string"
                ? details
                : JSON.stringify(details, null, 2)}
            </pre>
          ) : null}
          {copyError ? <p role="alert">无法复制，请手动选择错误码。</p> : null}
        </details>
      ) : null}
    </div>
  );
}

export const runLabels: Record<string, string> = {
  queued: "排队中",
  running: "计算中",
  succeeded: "计算完成",
  failed: "计算失败",
  cancelled: "已取消",
};
