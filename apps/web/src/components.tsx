import type { ReactNode, ComponentProps } from "react";
import { ApiError } from "./api";

const labels: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "运行中",
  SUCCEEDED: "已成功",
  FAILED: "失败",
  CANCELLED: "已取消",
  VALIDATED: "已验证",
  UNVALIDATED: "未验证",
  EXECUTABLE: "可执行",
  NOT_EXECUTABLE: "不可执行",
  MANUAL_REVIEW: "需人工复核",
  BLOCKED: "已阻断",
};
export function Status({ value }: { value: string }) {
  return (
    <span className={"status status-" + value.toLowerCase()}>
      {labels[value] ?? value}
    </span>
  );
}
export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div role="alert" className="error">
      <strong>操作未完成</strong>
      <p>{error instanceof Error ? error.message : "发生未知错误"}</p>
      {error instanceof ApiError ? (
        <small>
          {error.code}
          {error.requestId ? " · 追踪编号 " + error.requestId : ""}
        </small>
      ) : null}
    </div>
  );
}
export function Loading() {
  return (
    <p role="status" className="muted">
      正在读取数据…
    </p>
  );
}
export function PageTitle({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions}
    </div>
  );
}
export function Panel({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}
export function Details({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function display(value: unknown): string {
  return value === null || value === undefined
    ? "未提供"
    : typeof value === "string" ||
        typeof value === "number" ||
        typeof value === "boolean"
      ? String(value)
      : JSON.stringify(value);
}

export function DataTable({ className, ...props }: ComponentProps<"table">) {
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label={(props["aria-label"] ?? "数据表格") + "（可横向滚动）"}
    >
      <table
        className={["data-table", className].filter(Boolean).join(" ")}
        {...props}
      />
    </div>
  );
}
