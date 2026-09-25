import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, projectSchema, templateSchema } from "./api";
import { taskSchema, type Draft, type TaskRecord } from "./draft";
import { ErrorNotice } from "./shared";
import { ConflictPanel } from "./ConflictPanel";
import { useTaskDraft, saveMessage } from "./useTaskDraft";

type Json = z.infer<ReturnType<typeof z.json>>;
const recordSchema = z.record(z.string(), z.json());
const record = (value: unknown): Record<string, Json> => {
  const parsed = recordSchema.safeParse(value);
  return parsed.success ? parsed.data : {};
};
const text = (value: unknown) =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";
const numeric = (value: string) => (value === "" ? null : Number(value));

function useMethods(project: string) {
  return useQuery({
    queryKey: ["templates", project],
    queryFn: () =>
      api(`/projects/${project}/templates`, z.array(templateSchema)),
  });
}
function useRole(project: string) {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api("/projects", z.array(projectSchema)),
  });
  return projects.data?.find((p) => p.id === project)?.role;
}
const methodNames: Record<string, string> = {
  weighted: "固定权重综合评价",
  entropy: "熵权综合评价",
  topsis: "TOPSIS 贴近度评价",
  binary_allocation: "二元空间配置",
};
export function MethodSelector({
  task,
  change,
}: {
  task: TaskRecord;
  change: (edit: (draft: Draft) => Draft) => void;
}) {
  const methods = useMethods(task.project_id);
  const fixed = useQuery({
    queryKey: [
      "method-version",
      task.draft.method_id,
      task.draft.options.method_revision,
    ],
    enabled: !!task.draft.method_id && !!task.draft.options.method_revision,
    queryFn: () =>
      api(
        `/methods/${task.draft.method_id}/versions/${String(task.draft.options.method_revision)}`,
        templateSchema,
      ),
  });
  const candidates = [...(methods.data ?? [])];
  if (
    fixed.data &&
    !candidates.some(
      (m) => m.id === fixed.data?.id && m.revision === fixed.data.revision,
    )
  )
    candidates.push(fixed.data);
  const applicable = candidates.filter(
    (m) =>
      m.approved &&
      m.spec.purpose === "method" &&
      m.spec.configuration.task === task.draft.purpose,
  );
  const selected = applicable.find(
    (m) =>
      m.id === task.draft.method_id &&
      m.revision === task.draft.options.method_revision,
  );
  const selectedKey = task.draft.method_id
    ? `${task.draft.method_id}:${String(task.draft.options.method_revision)}`
    : "";
  return (
    <section>
      <h2>认可的方法</h2>
      <p>选择本次研究使用的方法版本。</p>
      <ErrorNotice error={methods.error ?? fixed.error} />
      <label>
        本次采用的方法
        <select
          value={selectedKey}
          onChange={(event) => {
            const method = applicable.find(
              (m) => `${m.id}:${m.revision}` === event.target.value,
            );
            change((draft) => ({
              ...draft,
              method_id: method?.id ?? null,
              options: {
                ...draft.options,
                method_revision: method?.revision ?? null,
              },
            }));
          }}
        >
          <option value="">请选择适用方法</option>
          {task.draft.method_id && !selected ? (
            <option value={selectedKey}>原方法版本正在核对或已不可用</option>
          ) : null}
          {applicable.map((method) => (
            <option
              key={`${method.id}:${method.revision}`}
              value={`${method.id}:${method.revision}`}
            >
              {method.spec.title} · v{method.revision}
            </option>
          ))}
        </select>
      </label>
      {selected ? (
        <>
          <p>依据：{selected.spec.basis}</p>
          <p>
            方法：
            {methodNames[text(selected.spec.configuration.method)] ??
              text(selected.spec.configuration.method)}
          </p>
          <ul>
            {(Array.isArray(selected.spec.configuration.indicators)
              ? selected.spec.configuration.indicators
              : Object.values(record(selected.spec.configuration.quantities))
            ).map((item, index) => {
              const entry = record(item);
              return (
                <li key={index}>
                  {text(entry.concept)} · {text(entry.unit)}
                  {entry.lower !== undefined
                    ? ` · 参考区间 ${text(entry.lower)} 至 ${text(entry.upper)} · ${entry.positive === true ? "正向" : "负向"}`
                    : ""}
                </li>
              );
            })}
          </ul>
        </>
      ) : (
        <p>
          {methods.isPending
            ? "正在读取方法…"
            : "如尚无适用方法，由维护者补充依据后交项目负责人认可。"}
        </p>
      )}
      <Link to={"/methods?project=" + task.project_id}>查看和维护方法</Link>
    </section>
  );
}
export function Methods({ project }: { project: string }) {
  const methods = useMethods(project),
    role = useRole(project),
    navigate = useNavigate(),
    cache = useQueryClient();
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("assessment");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  return (
    <>
      <h1>方法与依据</h1>
      <p>
        分析任务直接选用认可方法。维护草稿单独保存，修改后的定义需重新认可。
      </p>
      {role && role !== "viewer" ? (
        <section>
          <h2>维护新方法</h2>
          <form
            className="inline-form"
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError(null);
              try {
                const task = await api(
                  `/projects/${project}/method-drafts`,
                  taskSchema,
                  { method: "POST", body: JSON.stringify({ title, purpose }) },
                );
                navigate(`/tasks/${task.id}`);
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label>
              方法名称
              <input
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              适用任务
              <select
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
              >
                <option value="assessment">综合评价</option>
                <option value="optimization">空间优化</option>
              </select>
            </label>
            <button disabled={busy}>建立方法草稿</button>
          </form>
        </section>
      ) : null}
      <ErrorNotice error={error ?? methods.error} />
      <section>
        <h2>项目方法</h2>
        {methods.isPending ? (
          <p role="status">正在读取方法…</p>
        ) : !methods.data?.filter((m) => m.spec.purpose === "method").length ? (
          <p>暂无方法。先维护定义，认可后即可在项目任务中复用。</p>
        ) : (
          <ul className="task-list">
            {methods.data
              .filter((m) => m.spec.purpose === "method")
              .map((method) => (
                <li key={method.id}>
                  <div>
                    <strong>
                      {method.spec.title} · v{method.revision}
                    </strong>
                    <p>{method.spec.basis}</p>
                    <span>{method.approved ? "已认可" : "待认可"}</span>
                  </div>
                  {!method.approved && role === "manager" ? (
                    <button
                      disabled={busy}
                      type="button"
                      onClick={async () => {
                        setBusy(true);
                        setError(null);
                        try {
                          await api(
                            `/templates/${method.id}/approve`,
                            z.unknown(),
                            {
                              method: "POST",
                              body: JSON.stringify({
                                revision: method.revision,
                              }),
                            },
                          );
                          await cache.invalidateQueries({
                            queryKey: ["templates", project],
                          });
                        } catch (e) {
                          setError(e);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      认可此版本
                    </button>
                  ) : null}
                </li>
              ))}
          </ul>
        )}
      </section>
    </>
  );
}
const quantityNames: Record<string, string> = {
  benefit: "收益",
  cost: "成本",
  area: "面积",
  ecological_cost: "生态代价",
  risk: "风险指数",
};
export function MethodEditor({
  initial,
  canEdit = true,
}: {
  initial: TaskRecord;
  canEdit?: boolean;
}) {
  const { task, session, snapshot, replaceTask } = useTaskDraft(initial);
  const role = useRole(task.project_id),
    cache = useQueryClient();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const definition = record(task.draft.options.definition),
    configuration = record(definition.configuration);
  const assessment = task.draft.purpose === "assessment";
  const editDefinition = (key: string, value: Json) =>
    session.edit((draft) => ({
      ...draft,
      options: {
        ...draft.options,
        definition: { ...record(draft.options.definition), [key]: value },
      },
    }));
  const editConfiguration = (key: string, value: Json) =>
    session.edit((draft) => {
      const current = record(draft.options.definition);
      return {
        ...draft,
        options: {
          ...draft.options,
          definition: {
            ...current,
            configuration: { ...record(current.configuration), [key]: value },
          },
        },
      };
    });
  const indicators = Array.isArray(configuration.indicators)
    ? configuration.indicators.map(record)
    : [];
  const editIndicator = (index: number, key: string, value: Json) =>
    editConfiguration(
      "indicators",
      indicators.map((entry, i) =>
        i === index ? { ...entry, [key]: value } : entry,
      ),
    );
  const published = record(task.draft.options.publication);
  async function publish(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      await session.save();
      const response = await api(
        `/tasks/${task.id}/publish-method`,
        z.object({ template: templateSchema, task: taskSchema }),
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: session.snapshot().task.revision,
            approve,
          }),
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
  return (
    <>
      <Link to={"/methods?project=" + task.project_id}>← 方法与依据</Link>
      <div className="section-heading">
        <h1>维护{assessment ? "评价" : "优化"}方法</h1>
        <p role="status">{saveMessage(snapshot.status)}</p>
      </div>
      <ErrorNotice error={error ?? snapshot.error} />
      <ConflictPanel
        key={
          snapshot.conflicts.length
            ? JSON.stringify(snapshot.conflicts)
            : "none"
        }
        session={session}
        onResolved={() => setError(null)}
      />
      <form
        className="method-editor"
        onSubmit={(event) => {
          event.preventDefault();
          void publish(false);
        }}
      >
        <fieldset disabled={busy || !canEdit}>
          <legend>来源与适用范围</legend>
          <div className="form-grid">
            <label>
              方法名称
              <input
                required
                value={task.draft.title}
                onChange={(e) =>
                  session.edit((draft) => ({ ...draft, title: e.target.value }))
                }
              />
            </label>
            <label>
              方法依据
              <textarea
                required
                value={text(definition.basis)}
                onChange={(e) => editDefinition("basis", e.target.value)}
              />
            </label>
          </div>
          <fieldset>
            <legend>允许的数据类型</legend>
            <div className="actions">
              {Object.entries({
                csv: "分隔表格",
                csvw: "CSVW表格与元数据",
                geojson: "GeoJSON",
                geopackage: "GeoPackage",
                shapefile: "Shapefile",
              }).map(([key, label]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={
                      Array.isArray(definition.profiles) &&
                      definition.profiles.includes(key)
                    }
                    onChange={(e) => {
                      const selected = Array.isArray(definition.profiles)
                        ? definition.profiles
                        : [];
                      editDefinition(
                        "profiles",
                        e.target.checked
                          ? [...selected, key]
                          : selected.filter((item) => item !== key),
                      );
                    }}
                  />{" "}
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
        </fieldset>
        <fieldset disabled={busy || !canEdit}>
          <legend>{assessment ? "指标与评价规则" : "收益、成本与约束"}</legend>
          <label>
            计算方法
            <select
              required
              value={text(configuration.method)}
              onChange={(e) => {
                editConfiguration("method", e.target.value);
                if (e.target.value === "entropy")
                  editConfiguration(
                    "indicators",
                    indicators.map((entry) => ({ ...entry, weight: null })),
                  );
              }}
            >
              <option value="">请选择有依据的方法</option>
              {Object.entries(methodNames)
                .filter(([key]) =>
                  assessment
                    ? key !== "binary_allocation"
                    : key === "binary_allocation",
                )
                .map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
            </select>
          </label>
          {assessment ? (
            <>
              <p>
                区间、方向和权重应来自明确的方法依据。熵权法从本次有效观测计算权重；不自动填入相等权重。
              </p>
              {indicators.map((entry, index) => (
                <fieldset key={index}>
                  <legend>指标 {index + 1}</legend>
                  <div className="form-grid">
                    <label>
                      科学含义
                      <input
                        required
                        value={text(entry.concept)}
                        onChange={(e) =>
                          editIndicator(index, "concept", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      参考单位
                      <input
                        required
                        placeholder="如 m、km、1"
                        value={text(entry.unit)}
                        onChange={(e) =>
                          editIndicator(index, "unit", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      参考下限
                      <input
                        required
                        type="number"
                        step="any"
                        value={text(entry.lower)}
                        onChange={(e) =>
                          editIndicator(index, "lower", numeric(e.target.value))
                        }
                      />
                    </label>
                    <label>
                      参考上限
                      <input
                        required
                        type="number"
                        step="any"
                        value={text(entry.upper)}
                        onChange={(e) =>
                          editIndicator(index, "upper", numeric(e.target.value))
                        }
                      />
                    </label>
                    <label>
                      指标方向
                      <select
                        required
                        value={
                          entry.positive === true
                            ? "positive"
                            : entry.positive === false
                              ? "negative"
                              : ""
                        }
                        onChange={(e) =>
                          editIndicator(
                            index,
                            "positive",
                            e.target.value === ""
                              ? null
                              : e.target.value === "positive",
                          )
                        }
                      >
                        <option value="">待明确</option>
                        <option value="positive">数值越高越优</option>
                        <option value="negative">数值越低越优</option>
                      </select>
                    </label>
                    {configuration.method !== "entropy" ? (
                      <label>
                        认可权重
                        <input
                          required
                          type="number"
                          min="0"
                          step="any"
                          value={text(entry.weight)}
                          onChange={(e) =>
                            editIndicator(
                              index,
                              "weight",
                              numeric(e.target.value),
                            )
                          }
                        />
                      </label>
                    ) : null}
                  </div>
                  <button
                    className="secondary"
                    type="button"
                    onClick={() =>
                      editConfiguration(
                        "indicators",
                        indicators.filter((_, i) => i !== index),
                      )
                    }
                  >
                    移除指标 {index + 1}
                  </button>
                </fieldset>
              ))}
              <button
                className="secondary"
                type="button"
                onClick={() =>
                  editConfiguration("indicators", [
                    ...indicators,
                    {
                      concept: "",
                      unit: "",
                      lower: null,
                      upper: null,
                      positive: null,
                      weight: null,
                    },
                  ])
                }
              >
                添加指标定义
              </button>
            </>
          ) : (
            <>
              <p>
                候选单元从任务资料整体读取。这里定义字段含义和约束，不录入候选单元。
              </p>
              {Object.entries(quantityNames).map(([key, label]) => {
                const quantities = record(configuration.quantities),
                  item = record(quantities[key]);
                return (
                  <fieldset key={key}>
                    <legend>{label}定义</legend>
                    <div className="form-grid">
                      <label>
                        科学含义
                        <input
                          required
                          value={text(item.concept)}
                          onChange={(e) =>
                            editConfiguration("quantities", {
                              ...quantities,
                              [key]: { ...item, concept: e.target.value },
                            })
                          }
                        />
                      </label>
                      <label>
                        参考单位
                        <input
                          required
                          value={text(item.unit)}
                          onChange={(e) =>
                            editConfiguration("quantities", {
                              ...quantities,
                              [key]: { ...item, unit: e.target.value },
                            })
                          }
                        />
                      </label>
                    </div>
                  </fieldset>
                );
              })}
              <div className="form-grid">
                <label>
                  保护状态的科学含义
                  <input
                    required
                    value={text(configuration.protected_concept)}
                    onChange={(e) =>
                      editConfiguration("protected_concept", e.target.value)
                    }
                  />
                </label>
                <label>
                  风险汇总方式
                  <select
                    required
                    value={text(configuration.risk_aggregation)}
                    onChange={(e) =>
                      editConfiguration("risk_aggregation", e.target.value)
                    }
                  >
                    <option value="">请选择有依据的方式</option>
                    <option value="additive_index">可加风险指数</option>
                  </select>
                </label>
                <label>
                  可加性依据
                  <textarea
                    required
                    value={text(configuration.additivity_basis)}
                    onChange={(e) =>
                      editConfiguration("additivity_basis", e.target.value)
                    }
                  />
                </label>
                {Object.entries({
                  budget: "预算上限",
                  minimum_area: "面积下限",
                  maximum_ecological_cost: "生态代价上限",
                  maximum_risk: "风险上限",
                  time_limit: "求解时间上限（秒）",
                }).map(([key, label]) => (
                  <label key={key}>
                    {label}
                    <input
                      required
                      type="number"
                      min={key === "time_limit" ? 1 : 0}
                      max={key === "time_limit" ? 120 : undefined}
                      step="any"
                      value={text(configuration[key])}
                      onChange={(e) =>
                        editConfiguration(key, numeric(e.target.value))
                      }
                    />
                  </label>
                ))}
              </div>
              <p>
                各上限与下限使用对应参考单位。保护状态未知不能当作未保护，缺失成本不能当作零。
              </p>
            </>
          )}
        </fieldset>
        <div className="actions">
          <button
            disabled={
              busy ||
              !canEdit ||
              published.origin_revision === task.revision - 1
            }
          >
            发布待认可版本
          </button>
          {role === "manager" ? (
            <button
              type="button"
              className="secondary"
              disabled={
                busy ||
                !canEdit ||
                published.origin_revision === task.revision - 1
              }
              onClick={(event) => {
                if (event.currentTarget.form?.reportValidity())
                  void publish(true);
              }}
            >
              发布并认可方法
            </button>
          ) : null}
          {published.template_id ? (
            <p role="status">已发布方法版本；后续任务可从方法列表选用。</p>
          ) : null}
        </div>
      </form>
    </>
  );
}
