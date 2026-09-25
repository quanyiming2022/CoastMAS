import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";
import { api } from "./api";
import { taskSchema, type TaskRecord } from "./draft";
import { planningObjectSchema, type PlanningKind } from "./planningDraft";
import { ErrorNotice } from "./shared";

const names = {
  objectives: "规划目标",
  constraints: "约束",
  decisions: "决策变量",
};
const refSchema = z.object({
  object_id: z.string(),
  version_id: z.string(),
  version: z.number(),
  name: z.string().optional(),
  sha256: z.string(),
});
export function PlanningTaskBindings({
  task,
  kind,
  canEdit,
  onSaved,
  beforeSave,
}: {
  task: TaskRecord;
  kind: PlanningKind;
  canEdit: boolean;
  onSaved: (task: TaskRecord) => void;
  beforeSave: () => Promise<void>;
}) {
  const [search, setSearch] = useState(""),
    [choice, setChoice] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const listing = useQuery({
    queryKey: ["planning-binding-options", task.project_id, kind, search],
    queryFn: () =>
      api(
        `/v1/projects/${task.project_id}/planning/${kind}?search=${encodeURIComponent(search)}&limit=100`,
        z.object({ items: z.array(planningObjectSchema), total: z.number() }),
      ),
  });
  const refs = z
    .record(z.string(), refSchema)
    .safeParse(task.draft.options.planning_refs ?? {});
  const fixed = refs.success ? refs.data[kind] : undefined;
  async function apply() {
    setBusy(true);
    setError(null);
    try {
      await beforeSave();
      const selected = listing.data?.items
        .flatMap((item) =>
          item.versions.map((v) => ({ object_id: item.id, version_id: v.id })),
        )
        .find((v) => v.version_id === choice);
      if (!selected) throw new Error("请选择固定配置版本");
      const saved = await api(
        `/v1/tasks/${task.id}/planning/bindings`,
        taskSchema,
        {
          method: "POST",
          headers: { "If-Match": `"${task.revision}"` },
          body: JSON.stringify({ kind, ...selected }),
        },
      );
      onSaved(saved);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={names[kind] + "绑定"}>
      <h3>{names[kind]}</h3>
      <p>
        {fixed
          ? `已引用固定版本 v${fixed.version}${fixed.name ? " · " + fixed.name : ""}`
          : "尚未引用固定配置"}
      </p>
      <ErrorNotice error={listing.error ?? error} />
      <label>
        搜索已发布配置
        <input value={search} onChange={(e) => setSearch(e.target.value)} />
      </label>
      <label>
        固定版本
        <select
          disabled={!canEdit || busy}
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
        >
          <option value="">选择配置版本</option>
          {listing.data?.items.flatMap((item) =>
            item.versions.map((v) => (
              <option value={v.id} key={v.id}>
                {item.name} · v{v.version}
              </option>
            )),
          )}
        </select>
      </label>
      {(listing.data?.total ?? 0) > 100 ? <p>请搜索名称缩小范围。</p> : null}
      <button
        type="button"
        className="primary"
        disabled={!canEdit || busy || !choice}
        onClick={() => void apply()}
      >
        应用到当前研究
      </button>
      <Link to={`/planning/${kind}?project=${task.project_id}`}>
        管理{names[kind]}
      </Link>
    </section>
  );
}
