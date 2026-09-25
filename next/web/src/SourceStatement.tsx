import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, projectSchema } from "./api";
import { taskSchema, type Draft, type TaskRecord } from "./draft";
import { templateSchema } from "./api";
import { ErrorNotice } from "./shared";
const statementSchema = z.object({
  basis: z.string().optional(),
  source_description: z.string().nullable().optional(),
  license_statement: z.string().nullable().optional(),
  observed_year: z.number().nullable().optional(),
});
const declarationsSchema = z.record(
  z.string(),
  z.record(z.string(), z.union([z.string(), z.number(), z.null()])),
);
export function SourceStatement({
  task,
  edit,
  save,
  replaceTask,
  setBusy,
}: {
  task: TaskRecord;
  edit: (change: (draft: Draft) => Draft) => void;
  save: () => Promise<TaskRecord>;
  replaceTask: (task: TaskRecord) => void;
  setBusy: (busy: boolean) => void;
}) {
  const cache = useQueryClient();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api("/projects", z.array(projectSchema)),
  });
  const role = projects.data?.find(
    (project) => project.id === task.project_id,
  )?.role;
  const parsed = statementSchema.safeParse(
      task.draft.options.source_statement ?? {},
    ),
    current = parsed.success ? parsed.data : {};
  const inherited = declarationsSchema.safeParse(
    task.draft.options.inherited_declarations ?? {},
  );
  const [error, setError] = useState<unknown>(null);
  const change = (key: string, value: string | number | null) =>
    edit((draft) => ({
      ...draft,
      options: {
        ...draft.options,
        source_statement: { ...current, [key]: value },
      },
    }));
  async function publish(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      const latest = await save();
      const response = await api(
        `/tasks/${task.id}/publish-statement`,
        z.object({ task: taskSchema, template: templateSchema }),
        {
          method: "POST",
          body: JSON.stringify({ expected_revision: latest.revision, approve }),
        },
      );
      replaceTask(response.task);
      await cache.invalidateQueries({
        queryKey: ["templates", task.project_id],
      });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!task.draft.selection.length) return null;
  const known = task.draft.selection.filter(
    (source) =>
      inherited.success &&
      Object.keys(inherited.data[source.asset_id] ?? {}).length,
  );
  return (
    <section>
      <h2>来源与使用声明</h2>
      <p>作用于本次已选的 {task.draft.selection.length} 份输入资料。</p>
      {known.length ? (
        <details className="disclosure">
          <summary>{known.length} 份资料已沿用有效声明</summary>
          <ul>
            {known.map((source) => (
              <li key={source.asset_id}>
                {Object.entries(
                  inherited.success
                    ? (inherited.data[source.asset_id] ?? {})
                    : {},
                ).map(([key, value]) => (
                  <p key={key}>
                    {(
                      {
                        source: "资料来源",
                        use_restriction: "使用限制",
                        observed_year: "声明年份",
                        license: "许可说明",
                      } as Record<string, string>
                    )[key] ?? key}
                    ：{String(value ?? "未知")}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </details>
      ) : (
        <p>
          当前没有适用声明；资料可继续登记，正式使用需满足相应来源与许可要求。
        </p>
      )}
      <details className="disclosure">
        <summary>集中补充或修订声明</summary>
        <div className="form-grid">
          <label>
            资料来源说明
            <input
              value={current.source_description ?? ""}
              onChange={(e) =>
                change("source_description", e.target.value || null)
              }
            />
          </label>
          <label>
            使用许可或限制
            <input
              value={current.license_statement ?? ""}
              onChange={(e) =>
                change("license_statement", e.target.value || null)
              }
            />
          </label>
          <label>
            已知观测年份
            <input
              type="number"
              min="1"
              max="9999"
              step="1"
              value={current.observed_year ?? ""}
              onChange={(e) =>
                change(
                  "observed_year",
                  e.target.value ? Number(e.target.value) : null,
                )
              }
            />
          </label>
          <label>
            声明依据
            <textarea
              value={current.basis ?? ""}
              onChange={(e) => change("basis", e.target.value)}
            />
          </label>
        </div>
        <p>未知项留空；年份只表示观测年份，不补成具体日期。</p>
        <ErrorNotice error={error} />
        <div className="actions">
          {role && role !== "viewer" ? (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                void publish(role === "manager");
              }}
            >
              {role === "manager" ? "保存并认可本批声明" : "提交声明待认可"}
            </button>
          ) : null}
        </div>
      </details>
    </section>
  );
}
