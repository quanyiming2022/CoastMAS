import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import type { TaskRecord } from "./draft";
import type { ResearchStep } from "./ResearchPanels";
import { ErrorNotice } from "./shared";
const issueSchema = z.object({
  id: z.string(),
  code: z.string(),
  message: z.string(),
  steps: z.array(z.string()),
  action: z.string(),
  asset_id: z.string().nullable().optional(),
  concept: z.string().nullable().optional(),
  details: z.unknown().optional(),
});
const schema = z.object({
  task_id: z.string(),
  revision: z.number(),
  scope: z.literal("saved_metadata"),
  execution_checked: z.literal(false),
  issues: z.array(issueSchema),
});
export type ConfigurationIssue = z.infer<typeof issueSchema>;
export function useConfigurationReview(task?: TaskRecord) {
  const identity = task ? `${task.project_id}:${task.id}:${task.revision}` : "";
  const [settled, setSettled] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setSettled(identity), 250);
    return () => clearTimeout(timer);
  }, [identity]);
  const enabled = !!task?.draft.selection.length;
  const query = useQuery({
    queryKey: [
      "configuration-review",
      task?.project_id,
      task?.id,
      task?.revision,
    ],
    enabled: enabled && settled === identity,
    queryFn: async ({ signal }) => {
      const report = await api(
        `/tasks/${task!.id}/configuration-review?revision=${task!.revision}`,
        schema,
        { signal },
      );
      if (report.task_id !== task!.id || report.revision !== task!.revision)
        throw new Error("检查对应的配置已变化，请重新检查");
      return report;
    },
    staleTime: 15000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  return {
    state: !enabled
      ? "idle"
      : query.error
        ? "error"
        : settled !== identity || query.isFetching || !query.data
          ? "checking"
          : "checked",
    issues: query.error ? [] : (query.data?.issues ?? []),
    error: query.error,
    retry: () => {
      void query.refetch();
    },
  };
}
export type ConfigurationReview = ReturnType<typeof useConfigurationReview>;
const actions: Record<string, string> = {
  inputs: "选择资料",
  methods: "选择或修订方法",
  bindings: "核对指标",
  asset: "查看资料",
  lifecycle: "查看对象状态",
};
export function ConfigurationIssues({
  review,
  step,
  onAction,
}: {
  review: ConfigurationReview;
  step?: ResearchStep;
  onAction: (issue: ConfigurationIssue) => void;
}) {
  if (review.state === "idle") return null;
  if (review.state === "checking")
    return (
      <p role="status" className="compact-status">
        正在检查配置…
      </p>
    );
  if (review.state === "error")
    return (
      <section className="configuration-issues" aria-label="配置检查">
        <p role="alert">检查未完成</p>
        <button type="button" className="secondary" onClick={review.retry}>
          重新检查
        </button>
        <details>
          <summary>检查错误详情</summary>
          <ErrorNotice error={review.error} />
        </details>
      </section>
    );
  const issues = [
    ...new Map(
      review.issues
        .filter((i) => !step || i.steps.includes(step))
        .map((i) => [i.id, i]),
    ).values(),
  ];
  if (!issues.length) return null;
  return (
    <section className="configuration-issues" aria-label="待处理">
      <h3>待处理</h3>
      <ul>
        {issues.map((issue) => (
          <li key={issue.id}>
            <p>{issue.message}</p>
            <button
              type="button"
              className="text-button"
              onClick={() => onAction(issue)}
            >
              {actions[issue.action] ?? "查看问题"}
            </button>
            {issue.details !== undefined && issue.details !== null ? (
              <details>
                <summary>问题详情</summary>
                <pre>{JSON.stringify(issue.details, null, 2)}</pre>
              </details>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
