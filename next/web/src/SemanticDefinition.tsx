import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, projectSchema, templateSchema, type Asset } from "./api";
import { taskSchema, type TaskRecord, type Draft } from "./draft";
import { ErrorNotice } from "./shared";
const editorSchema = z.object({
  basis: z.string().optional(),
  scope: z.enum(["files", "same_names"]).optional(),
});
export function SemanticDefinition({
  task,
  assets,
  edit,
  save,
  replaceTask,
  setBusy,
}: {
  task: TaskRecord;
  assets: Asset[];
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
  const parsed = editorSchema.safeParse(
    task.draft.options.semantic_definition ?? {},
  );
  const current = parsed.success ? parsed.data : {};
  const known = task.draft.mapping.filter(
    (binding) => binding.concept || binding.unit || binding.support,
  );
  const applicable = assets.filter((asset) =>
    known.some((binding) => binding.asset_id === asset.id),
  );
  const [error, setError] = useState<unknown>(null);
  function change(key: "basis" | "scope", value: string) {
    edit((draft) => ({
      ...draft,
      options: {
        ...draft.options,
        semantic_definition: { ...current, [key]: value },
      },
    }));
  }
  async function publish() {
    setBusy(true);
    setError(null);
    try {
      const latest = await save();
      const response = await api(
        `/tasks/${task.id}/publish-definition`,
        z.object({ task: taskSchema, template: templateSchema }),
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: latest.revision,
            approve: role === "manager",
          }),
        },
      );
      replaceTask(response.task);
      await cache.invalidateQueries({
        queryKey: ["templates", task.project_id],
      });
    } catch (error) {
      setError(error);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="disclosure">
      <summary>将已知指标定义保存为项目依据</summary>
      <p>
        科学含义、单位和观测支撑可复用；本任务的响应变量选择、年份、方法权重不会随定义复制。未知项保持为空。
      </p>
      <p>
        当前可保存 {known.length} 个字段，涉及 {applicable.length} 份资料：
        {applicable.map((asset) => asset.name).join("、") || "尚无已知定义"}。
      </p>
      <div className="form-grid">
        <label>
          定义适用范围
          <select
            value={current.scope ?? "files"}
            onChange={(event) => change("scope", event.target.value)}
          >
            <option value="files">仅当前实际文件</option>
            <option value="same_names">本项目后续同名、同结构资料</option>
          </select>
        </label>
        <label>
          指标定义依据
          <textarea
            value={current.basis ?? ""}
            onChange={(event) => change("basis", event.target.value)}
          />
        </label>
      </div>
      {current.scope === "same_names" ? (
        <p>
          请确认上述名称代表同一类科学资料。新批次仍重新读取字节、格式、版本和字段，再沿用有效定义；同名不代表自动认可新的来源与时期。
        </p>
      ) : null}
      <ErrorNotice error={error} />
      {role && role !== "viewer" ? (
        <button
          type="button"
          className="secondary"
          disabled={!known.length || !current.basis?.trim()}
          onClick={() => void publish()}
        >
          {role === "manager" ? "保存并认可指标定义" : "提交指标定义待认可"}
        </button>
      ) : null}
    </details>
  );
}
