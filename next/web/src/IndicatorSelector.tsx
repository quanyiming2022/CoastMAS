import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, jobSchema } from "./api";
import { taskSchema, type TaskRecord } from "./draft";
import { ErrorNotice } from "./shared";

const candidateSchema = z.object({
  key: z.string(),
  label: z.string(),
  mode: z.string(),
  status: z.string(),
  message: z.string().nullable(),
});
const itemSchema = z.object({
  indicator_id: z.string(),
  name: z.string(),
  category: z.string(),
  description: z.string(),
  status: z.string(),
  message: z.string(),
  missing: z.array(z.string()),
  suggested_key: z.string().nullable().optional(),
  installation_status: z.string(),
  candidates: z.array(candidateSchema),
  business_parameters: z.array(
    z.object({ name: z.string(), label: z.string(), default: z.number() }),
  ),
});
const selectionSchema = z.object({
  selection_id: z.string(),
  indicator_id: z.string(),
  mode: z.string().nullable(),
  status: z.string(),
});
const catalogSchema = z.object({
  task_id: z.string(),
  revision: z.number(),
  items: z.array(itemSchema),
  selected: z.array(selectionSchema),
});
const chosenSchema = z.object({
  task: taskSchema,
  items: z.array(selectionSchema),
});
const statusNames: Record<string, string> = {
  ready: "已满足",
  missing: "需数据",
  ambiguous: "选择来源",
  adaptation: "可适配",
  inapplicable: "需核对",
  not_installed: "研发中",
};

export function IndicatorSelector({
  task,
  save,
  replace,
  onRun,
  onAddData,
}: {
  task: TaskRecord;
  save: () => Promise<TaskRecord>;
  replace: (task: TaskRecord) => void;
  onRun: (job: z.infer<typeof jobSchema>) => void;
  onAddData: () => void;
}) {
  const cache = useQueryClient();
  const [search, setSearch] = useState(""),
    [category, setCategory] = useState(""),
    [status, setStatus] = useState(""),
    [onlyFavorites, setOnlyFavorites] = useState(false);
  const [checked, setChecked] = useState<string[]>([]),
    [candidates, setCandidates] = useState<Record<string, string>>({});
  const [parameters, setParameters] = useState<
    Record<string, Record<string, number>>
  >({});
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const [favorites, setFavorites] = useState<string[]>(() => {
    try {
      return z
        .array(z.string())
        .parse(
          JSON.parse(
            localStorage.getItem("coastmas.indicator-favorites") ?? "[]",
          ),
        );
    } catch {
      return [];
    }
  });
  const active = useRef(task.id);
  useEffect(() => {
    active.current = task.id;
    return () => {
      active.current = "";
    };
  }, [task.id]);
  const catalog = useQuery({
    queryKey: ["builtin-indicators", task.id, task.revision],
    queryFn: () => api(`/v1/tasks/${task.id}/indicators`, catalogSchema),
  });
  const installed =
    catalog.data?.items.filter((i) => i.installation_status === "published") ??
    [];
  const visible = installed.filter(
    (i) =>
      (!search ||
        (i.name + i.description)
          .toLowerCase()
          .includes(search.toLowerCase())) &&
      (!category || i.category === category) &&
      (!status ||
        (status === "ready" ? i.status === "ready" : i.status !== "ready")) &&
      (!onlyFavorites || favorites.includes(i.indicator_id)),
  );
  function favorite(id: string) {
    const next = favorites.includes(id)
      ? favorites.filter((x) => x !== id)
      : [...favorites, id];
    setFavorites(next);
    try {
      localStorage.setItem(
        "coastmas.indicator-favorites",
        JSON.stringify(next),
      );
    } catch {
      /* UI preference storage is optional. */
    }
  }
  async function choose(ids: string[]) {
    setBusy(true);
    setError(null);
    const taskId = task.id;
    try {
      const saved = await save();
      const result = await api(`/v1/tasks/${taskId}/indicators`, chosenSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: saved.revision,
          idempotency_key: crypto.randomUUID(),
          items: ids.map((indicator_id) => ({
            indicator_id,
            ...(candidates[indicator_id]
              ? { candidate_key: candidates[indicator_id] }
              : {}),
            parameters: parameters[indicator_id] ?? {},
          })),
        }),
      });
      if (active.current !== taskId) return;
      replace(result.task);
      setChecked([]);
      await cache.invalidateQueries({
        queryKey: ["builtin-indicators", taskId],
      });
    } catch (e) {
      if (active.current === taskId) setError(e);
    } finally {
      if (active.current === taskId) setBusy(false);
    }
  }
  async function run(selectionId: string) {
    setBusy(true);
    setError(null);
    const taskId = task.id;
    try {
      const saved = await save();
      const job = await api(
        `/v1/tasks/${taskId}/indicators/${selectionId}/execute`,
        jobSchema,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: saved.revision,
            idempotency_key: crypto.randomUUID(),
          }),
        },
      );
      const current = await api(`/tasks/${taskId}`, taskSchema);
      if (active.current !== taskId) return;
      replace(current);
      onRun(job);
    } catch (e) {
      if (active.current === taskId) setError(e);
    } finally {
      if (active.current === taskId) setBusy(false);
    }
  }
  return (
    <section className="indicator-selector" aria-label="指标选择器">
      <div className="indicator-search-tools">
        <input
          aria-label="搜索指标"
          placeholder="搜索指标"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="指标分类"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">全部分类</option>
          {[...new Set(installed.map((i) => i.category))].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select
          aria-label="数据满足状态"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">全部状态</option>
          <option value="ready">已满足</option>
          <option value="missing">需数据/核对</option>
        </select>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={onlyFavorites}
            onChange={(e) => setOnlyFavorites(e.target.checked)}
          />
          我的常用
        </label>
      </div>
      <ErrorNotice error={error ?? catalog.error} />
      {catalog.isPending ? <p role="status">正在匹配已有数据…</p> : null}
      {checked.length ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => void choose(checked)}
        >
          添加所选 {checked.length} 项
        </button>
      ) : null}
      {!catalog.isPending && !catalog.error && !visible.length ? (
        <p>没有符合筛选的可用指标。</p>
      ) : null}
      <ul className="indicator-candidates">
        {visible.map((item) => {
          const selected = catalog.data?.selected.find(
            (s) => s.indicator_id === item.indicator_id,
          );
          return (
            <li key={item.indicator_id}>
              <div className="indicator-row-heading">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={checked.includes(item.indicator_id)}
                    onChange={(e) =>
                      setChecked(
                        e.target.checked
                          ? [...checked, item.indicator_id]
                          : checked.filter((x) => x !== item.indicator_id),
                      )
                    }
                  />
                  <strong>{item.name}</strong>
                </label>
                <button
                  type="button"
                  className="text-button"
                  aria-label={`常用 ${item.name}`}
                  aria-pressed={favorites.includes(item.indicator_id)}
                  onClick={() => favorite(item.indicator_id)}
                >
                  {favorites.includes(item.indicator_id) ? "已常用" : "常用"}
                </button>
              </div>
              <p className="indicator-description">{item.description}</p>
              <p>
                <span className="status-chip">
                  {statusNames[item.status] ?? item.status}
                </span>{" "}
                {item.message}
              </p>
              {item.candidates.length > 1 || item.status === "ambiguous" ? (
                <label>
                  数据来源
                  <select
                    aria-label={`${item.name}数据来源`}
                    value={
                      candidates[item.indicator_id] ?? item.suggested_key ?? ""
                    }
                    onChange={(e) =>
                      setCandidates({
                        ...candidates,
                        [item.indicator_id]: e.target.value,
                      })
                    }
                  >
                    <option value="">选择适用来源</option>
                    {item.candidates.map((c) => (
                      <option key={c.key} value={c.key}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {item.business_parameters.length ? (
                <details>
                  <summary>高级设置</summary>
                  {item.business_parameters.map((p) => (
                    <label key={p.name}>
                      {p.label}
                      <input
                        type="number"
                        value={
                          parameters[item.indicator_id]?.[p.name] ?? p.default
                        }
                        onChange={(e) =>
                          setParameters({
                            ...parameters,
                            [item.indicator_id]: {
                              ...parameters[item.indicator_id],
                              [p.name]: e.target.valueAsNumber,
                            },
                          })
                        }
                      />
                    </label>
                  ))}
                </details>
              ) : null}
              <div className="indicator-row-actions">
                <button
                  type="button"
                  disabled={
                    busy ||
                    (!candidates[item.indicator_id] &&
                      item.status === "ambiguous")
                  }
                  className={selected ? "secondary" : "primary"}
                  onClick={() => void choose([item.indicator_id])}
                >
                  {selected ? "更新选择" : "添加"}
                </button>
                {item.status === "missing" ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={onAddData}
                  >
                    补充数据
                  </button>
                ) : null}
                {selected && selected.mode !== "existing" ? (
                  <button
                    type="button"
                    disabled={busy || item.status !== "ready"}
                    className="primary"
                    onClick={() => void run(selected.selection_id)}
                  >
                    计算{item.name}
                  </button>
                ) : null}
                {selected?.mode === "existing" ? (
                  <span>已引用成品指标</span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
