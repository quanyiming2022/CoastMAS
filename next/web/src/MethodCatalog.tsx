import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError, projectSchema } from "./api";
import { ManagedCatalog, Modal, type CatalogRow } from "./ManagedCatalog";
import { AhpMatrix, blankAhp } from "./AhpMatrix";
import { OptimizationRules, emptyOptimization } from "./OptimizationRules";
import { ErrorNotice } from "./shared";

const indicatorSchema = z.object({
  concept: z.string().default(""),
  unit: z.string().default(""),
  lower: z.number().nullable().default(null),
  upper: z.number().nullable().default(null),
  positive: z.boolean().nullable().default(null),
  weight: z.number().nullable().default(null),
});
const definitionSchema = z
  .object({
    title: z.string(),
    purpose: z.literal("method"),
    basis: z.string().default(""),
    profiles: z.array(z.string()).default([]),
    configuration: z
      .object({
        task: z.string(),
        method: z.string(),
        indicators: z.array(indicatorSchema).optional(),
      })
      .passthrough(),
  })
  .passthrough();
type Definition = z.infer<typeof definitionSchema>;
const workspaceSchema = z
  .object({
    id: z.string(),
    revision: z.number(),
    definition: definitionSchema,
    publication: z
      .object({ origin_revision: z.number() })
      .passthrough()
      .nullable(),
  })
  .passthrough();
type Workspace = z.infer<typeof workspaceSchema>;
const fieldNames: Record<string, string> = {
  concept: "指标",
  unit: "单位",
  lower: "下限",
  upper: "上限",
  positive: "方向",
  weight: "权重",
};
const blank: Definition = {
  title: "未命名方法",
  purpose: "method",
  basis: "",
  profiles: ["csv", "csvw", "geotiff", "geojson", "geopackage"],
  configuration: { task: "assessment", method: "weighted", indicators: [] },
};

export function MethodCatalog({
  project,
  active,
  canEdit,
  onOpen,
  editorHost,
  onEditing,
}: {
  project: string;
  active: boolean;
  canEdit: boolean;
  onOpen: (row: CatalogRow) => void;
  editorHost?: HTMLElement | null;
  onEditing?: (editing: boolean) => void;
}) {
  const cache = useQueryClient();
  const drafts = useQuery({
    queryKey: ["method-workspaces", project],
    enabled: active,
    queryFn: () =>
      api(`/projects/${project}/method-workspaces`, z.array(workspaceSchema)),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api("/projects", z.array(projectSchema)),
  });
  const canApprove =
    projects.data?.find((p) => p.id === project)?.role === "manager";
  const [editor, setEditor] = useState<Workspace | null>(null),
    [failure, setFailure] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [importing, setImporting] = useState(false);
  useEffect(() => {
    onEditing?.(!!editor && active);
  }, [editor, active, onEditing]);
  const [file, setFile] = useState<File | null>(null),
    [columns, setColumns] = useState<string[]>([]),
    [mapping, setMapping] = useState<Record<string, string>>({});
  async function refresh() {
    await cache.invalidateQueries({ queryKey: ["method-workspaces", project] });
    await cache.invalidateQueries({ queryKey: ["managed-catalog", "methods"] });
  }
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setFailure(null);
    try {
      await work();
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }
  async function start(row?: CatalogRow, mode: "clone" | "revise" = "clone") {
    const value = row
      ? await api(`/methods/${row.id}/edit`, workspaceSchema, {
          method: "POST",
          body: JSON.stringify({ revision: row.source_revision, mode }),
        })
      : await api(`/projects/${project}/method-workspaces`, workspaceSchema, {
          method: "POST",
          body: JSON.stringify({ definition: blank }),
        });
    setEditor(value);
    await refresh();
  }
  async function importFile() {
    if (!file) return;
    const body = new FormData();
    body.set("file", file);
    if (columns.length) body.set("mapping", JSON.stringify(mapping));
    try {
      const value = await api(
        `/projects/${project}/method-imports`,
        workspaceSchema,
        { method: "POST", body },
      );
      setEditor(value);
      setImporting(false);
      setColumns([]);
      setMapping({});
      await refresh();
    } catch (error) {
      if (error instanceof APIError && error.code === "METHOD_COLUMN_MAPPING") {
        const details = z
          .object({
            columns: z.array(z.string()),
            mapping: z.record(z.string(), z.string()),
          })
          .parse(error.details);
        setColumns(details.columns);
        setMapping(details.mapping);
      }
      throw error;
    }
  }
  return (
    <>
      <ManagedCatalog
        kind="methods"
        project={project}
        active={active}
        onOpen={onOpen}
        onNew={canEdit ? () => void action(() => start()) : undefined}
        toolbarExtras={
          <>
            <button
              type="button"
              className="secondary"
              disabled={!canEdit}
              onClick={() => {
                setFailure(null);
                setImporting(true);
              }}
            >
              导入方法
            </button>
            <label className="method-draft-picker">
              继续草稿
              <select
                aria-label="继续方法草稿"
                value=""
                disabled={!canEdit}
                onChange={(e) => {
                  const draft = drafts.data?.find(
                    (d) => d.id === e.target.value,
                  );
                  if (draft) setEditor(draft);
                }}
              >
                <option value="">选择未完成草稿</option>
                {drafts.data
                  ?.filter(
                    (d) =>
                      !d.publication ||
                      d.revision > d.publication.origin_revision + 1,
                  )
                  .map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.definition.title} · 草稿v{d.revision}
                    </option>
                  ))}
              </select>
            </label>
          </>
        }
        extraActions={(row) => (
          <>
            <button
              type="button"
              className="secondary"
              disabled={!canEdit || busy}
              onClick={() => void action(() => start(row, "clone"))}
            >
              克隆
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!canEdit || busy}
              onClick={() => void action(() => start(row, "revise"))}
            >
              修订
            </button>
            <a
              href={`/api/methods/${row.id}/versions/${String(row.source_revision)}/export`}
            >
              导出方法
            </a>
          </>
        )}
      />
      <ErrorNotice error={failure ?? drafts.error} />
      {importing ? (
        <Modal title="导入方法方案" close={() => setImporting(false)}>
          <label>
            选择方案文件
            <input
              type="file"
              accept=".json,.yaml,.yml,.csv,.xlsx"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setColumns([]);
                setMapping({});
                setFailure(null);
              }}
            />
          </label>
          <p>
            方法档案自动识别版本；指标表自动匹配列名。导入形成草稿，未提供的科学依据留空。
          </p>
          {columns.length ? (
            <div className="method-form-grid">
              {Object.entries(fieldNames).map(([key, label]) => (
                <label key={key}>
                  {label}
                  <select
                    value={mapping[key] ?? ""}
                    onChange={(e) =>
                      setMapping({ ...mapping, [key]: e.target.value })
                    }
                  >
                    <option value="">选择对应列</option>
                    {columns.map((column) => (
                      <option key={column}>{column}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          ) : null}
          <button
            type="button"
            disabled={!file || busy}
            onClick={() => void action(importFile)}
          >
            读取并建立草稿
          </button>
          <ErrorNotice error={failure} />
        </Modal>
      ) : null}
      {editor && editorHost
        ? createPortal(
            <MethodEditor
              key={editor.id}
              initial={editor}
              project={project}
              canApprove={canApprove}
              close={() => {
                setEditor(null);
                void refresh();
              }}
              published={() => void refresh()}
            />,
            editorHost,
          )
        : null}
    </>
  );
}

function MethodEditor({
  initial,
  project,
  canApprove,
  close,
  published,
}: {
  initial: Workspace;
  project: string;
  canApprove: boolean;
  close: () => void;
  published: () => void;
}) {
  const [value, setValue] = useState(initial),
    [status, setStatus] = useState("已保存"),
    [error, setError] = useState<unknown>(null),
    [publishing, setPublishing] = useState(false);
  const current = useRef(initial),
    saved = useRef(initial.definition),
    pending = useRef<Promise<void> | null>(null),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [indicatorLibrary, setIndicatorLibrary] = useState(false),
    [indicatorSearch, setIndicatorSearch] = useState("");
  const definitions = useQuery({
    queryKey: ["indicator-definitions", project],
    enabled: indicatorLibrary,
    queryFn: () =>
      api(
        `/projects/${project}/indicator-definitions`,
        z.array(
          z.object({
            id: z.string(),
            source: z.string(),
            revision: z.number(),
            basis: z.string(),
            indicator: indicatorSchema,
          }),
        ),
      ),
  });
  async function importIndicators(file: File) {
    setPublishing(true);
    setError(null);
    try {
      await flush();
      const body = new FormData();
      body.set("file", file);
      body.set("expected_revision", String(current.current.revision));
      const next = await api(
        `/method-workspaces/${current.current.id}/indicators:import`,
        workspaceSchema,
        { method: "POST", body },
      );
      current.current = next;
      saved.current = next.definition;
      setValue(next);
      setStatus("已保存");
    } catch (failure) {
      setError(failure);
      setStatus("导入失败，原草稿保留");
    } finally {
      setPublishing(false);
    }
  }
  async function flush(): Promise<void> {
    if (timer.current) clearTimeout(timer.current);
    if (pending.current) {
      await pending.current;
      if (saved.current !== current.current.definition) return flush();
      return;
    }
    if (saved.current === current.current.definition) return;
    const snapshot = current.current;
    setStatus("保存中");
    setError(null);
    const request = api(`/method-workspaces/${snapshot.id}`, workspaceSchema, {
      method: "PUT",
      body: JSON.stringify({
        expected_revision: snapshot.revision,
        definition: snapshot.definition,
      }),
    })
      .then((next) => {
        saved.current = snapshot.definition;
        current.current = { ...next, definition: current.current.definition };
        setValue(current.current);
        setStatus(
          saved.current === current.current.definition ? "已保存" : "待保存",
        );
      })
      .catch((failure) => {
        setError(failure);
        setStatus(
          failure instanceof APIError && failure.status === 409
            ? "保存冲突"
            : "保存失败",
        );
        throw failure;
      });
    pending.current = request;
    try {
      await request;
    } finally {
      pending.current = null;
    }
    if (saved.current !== current.current.definition) await flush();
  }
  function change(definition: Definition) {
    current.current = { ...current.current, definition };
    setValue(current.current);
    setStatus("待保存");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void flush().catch(() => {});
    }, 400);
  }
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (saved.current !== current.current.definition) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      window.removeEventListener("beforeunload", warn);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);
  const definition = value.definition,
    config = definition.configuration,
    rows = config.indicators ?? [];
  function rowChange(
    index: number,
    key: string,
    entry: string | number | boolean | null,
  ) {
    change({
      ...definition,
      configuration: {
        ...config,
        indicators: rows.map((row, n) =>
          n === index ? { ...row, [key]: entry } : row,
        ),
      },
    });
  }
  async function publish() {
    setPublishing(true);
    setError(null);
    try {
      await flush();
      const result = await api(
        `/method-workspaces/${value.id}/publish`,
        z.object({ workspace: workspaceSchema, template: z.unknown() }),
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: current.current.revision,
            approve: false,
          }),
        },
      );
      current.current = result.workspace;
      saved.current = result.workspace.definition;
      setValue(result.workspace);
      setStatus("已发布，待批准");
      published();
    } catch (failure) {
      setError(failure);
      setStatus("草稿已保存，尚未发布");
    } finally {
      setPublishing(false);
    }
  }
  const publication = z
    .object({ template_id: z.string(), template_revision: z.number() })
    .safeParse(value.publication);
  async function approvePublished() {
    if (!publication.success) return;
    setPublishing(true);
    setError(null);
    try {
      await api(
        `/templates/${publication.data.template_id}/approve`,
        z.object({ approved: z.boolean() }),
        {
          method: "POST",
          body: JSON.stringify({
            revision: publication.data.template_revision,
          }),
        },
      );
      setStatus("已批准第" + publication.data.template_revision + "版");
      published();
    } catch (failure) {
      setError(failure);
    } finally {
      setPublishing(false);
    }
  }
  const publicationIssues =
    error instanceof APIError
      ? z
          .object({
            issues: z.array(
              z.object({ field: z.string(), message: z.string() }),
            ),
          })
          .safeParse(error.details)
      : null;
  return (
    <section aria-label="方法方案编辑" className="method-workspace-editor">
      {indicatorLibrary ? (
        <Modal
          title="选择已有指标定义"
          close={() => setIndicatorLibrary(false)}
        >
          <label>
            搜索指标
            <input
              type="search"
              value={indicatorSearch}
              onChange={(e) => setIndicatorSearch(e.target.value)}
            />
          </label>
          <ErrorNotice error={definitions.error} />
          {definitions.isPending ? <p>读取中…</p> : null}
          {definitions.data?.length === 0 ? (
            <p>项目内尚无已批准的指标定义，可导入指标表或添加新指标。</p>
          ) : null}
          <ul>
            {definitions.data
              ?.filter((item) =>
                (item.indicator.concept + item.source).includes(
                  indicatorSearch,
                ),
              )
              .map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => {
                      change({
                        ...definition,
                        configuration: {
                          ...config,
                          indicators: [...rows, item.indicator],
                        },
                      });
                      setIndicatorLibrary(false);
                    }}
                  >
                    {item.indicator.concept} ·{" "}
                    {item.indicator.unit || "单位待补"} · {item.source} 第
                    {item.revision}版
                  </button>
                  <details>
                    <summary>定义依据</summary>
                    {item.basis}
                  </details>
                </li>
              ))}
          </ul>
        </Modal>
      ) : null}
      <div className="method-editor">
        <div className="method-editor-toolbar">
          <label>
            方法名称
            <input
              value={definition.title}
              onChange={(e) => change({ ...definition, title: e.target.value })}
            />
          </label>
          <span role="status">{status}</span>
          <span>方法草稿 v{value.revision}</span>
          <button
            type="button"
            className="secondary"
            onClick={() => void flush().catch(() => {})}
          >
            保存草稿
          </button>

          <button
            type="button"
            disabled={publishing}
            onClick={() => void publish()}
          >
            发布固定版本
          </button>
          {canApprove && publication.success ? (
            <button
              type="button"
              className="secondary"
              disabled={publishing}
              onClick={() => void approvePublished()}
            >
              批准第{publication.data.template_revision}版
            </button>
          ) : null}
          <button
            type="button"
            className="secondary"
            onClick={() =>
              void flush()
                .then(close)
                .catch(() => {})
            }
          >
            返回方法目录
          </button>
        </div>

        {config.task === "assessment" ? (
          <>
            <div className="section-heading">
              <h3 id="method-indicators">指标与评分</h3>
              <button
                type="button"
                className="secondary"
                onClick={() => setIndicatorLibrary(true)}
              >
                从指标库选择
              </button>
              <label className="indicator-import-label">
                导入指标表
                <input
                  type="file"
                  accept=".csv,.xlsx"
                  disabled={publishing}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = "";
                    if (file) void importIndicators(file);
                  }}
                />
              </label>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  change({
                    ...definition,
                    configuration: {
                      ...config,
                      indicators: [
                        ...rows,
                        {
                          concept: "",
                          unit: "",
                          lower: null,
                          upper: null,
                          positive: null,
                          weight: null,
                        },
                      ],
                    },
                  })
                }
              >
                添加指标
              </button>
            </div>
            {!rows.length ? (
              <p>尚未添加指标</p>
            ) : (
              <div className="table-scroll">
                <table className="method-indicators">
                  <thead>
                    <tr>
                      <th>指标科学含义</th>
                      <th>单位</th>
                      <th>参考下限</th>
                      <th>参考上限</th>
                      <th>方向</th>
                      {config.method !== "entropy" && !config.weighting ? (
                        <th>权重</th>
                      ) : null}
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={index}>
                        {(["concept", "unit", "lower", "upper"] as const).map(
                          (key) => (
                            <td key={key}>
                              <input
                                aria-label={`第${index + 1}项${fieldNames[key]}`}
                                type={
                                  key === "concept" || key === "unit"
                                    ? "text"
                                    : "number"
                                }
                                step="any"
                                value={row[key] ?? ""}
                                onChange={(e) =>
                                  rowChange(
                                    index,
                                    key,
                                    key === "concept" || key === "unit"
                                      ? e.target.value
                                      : e.target.value === ""
                                        ? null
                                        : Number(e.target.value),
                                  )
                                }
                              />
                            </td>
                          ),
                        )}
                        <td>
                          <select
                            aria-label={`第${index + 1}项方向`}
                            value={
                              row.positive === null
                                ? ""
                                : row.positive
                                  ? "positive"
                                  : "negative"
                            }
                            onChange={(e) =>
                              rowChange(
                                index,
                                "positive",
                                e.target.value === ""
                                  ? null
                                  : e.target.value === "positive",
                              )
                            }
                          >
                            <option value="">选择方向</option>
                            <option value="positive">正向</option>
                            <option value="negative">负向</option>
                          </select>
                        </td>
                        {config.method !== "entropy" && !config.weighting ? (
                          <td>
                            <input
                              aria-label={`第${index + 1}项权重`}
                              type="number"
                              step="any"
                              min="0"
                              value={row.weight ?? ""}
                              disabled={
                                config.method === "entropy" ||
                                !!config.weighting
                              }
                              onChange={(e) =>
                                rowChange(
                                  index,
                                  "weight",
                                  e.target.value === ""
                                    ? null
                                    : Number(e.target.value),
                                )
                              }
                            />
                          </td>
                        ) : null}
                        <td>
                          <button
                            type="button"
                            className="secondary"
                            aria-label={`移除第${index + 1}项指标`}
                            onClick={() =>
                              change({
                                ...definition,
                                configuration: {
                                  ...config,
                                  indicators: rows.filter(
                                    (_, n) => n !== index,
                                  ),
                                },
                              })
                            }
                          >
                            移除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <h3 id="method-weighting">赋权方式</h3>
            <div className="method-form-grid">
              <label>
                综合方式
                <select
                  value={config.weighting ? "ahp" : config.method}
                  onChange={(e) => {
                    const method = e.target.value;
                    if (method === "ahp") {
                      change({
                        ...definition,
                        configuration: {
                          task: "assessment",
                          method: "weighted",
                          indicators: rows.map((row) => ({
                            ...row,
                            weight: null,
                          })),
                          weighting: blankAhp(rows.map((row) => row.concept)),
                        },
                      });
                      return;
                    }
                    if (method === "binary_allocation") {
                      if (
                        rows.length &&
                        !window.confirm(
                          "切换为空间优化会替换本草稿的评价指标配置；已发布版本保持不变。继续？",
                        )
                      )
                        return;
                      change({
                        ...definition,
                        configuration: emptyOptimization,
                      });
                      return;
                    }
                    change({
                      ...definition,
                      configuration: {
                        ...(config.task === "assessment"
                          ? config
                          : { task: "assessment" }),
                        method,
                        weighting: null,
                        indicators: rows.map((row) => ({
                          ...row,
                          weight: method === "entropy" ? null : row.weight,
                        })),
                      },
                    });
                  }}
                >
                  <option value="weighted">明确权重加权综合</option>
                  <option value="ahp">AHP判断赋权综合</option>
                  <option value="entropy">熵权综合</option>
                  <option value="topsis">TOPSIS排序</option>
                  <option value="binary_allocation">空间布局优化</option>
                </select>
              </label>
            </div>
            {rows.length ? (
              <p>
                {config.weighting
                  ? "权重来自以下固定AHP判断矩阵。"
                  : config.method === "entropy"
                    ? "熵权由实际归一化指标计算，不填写固定权重。"
                    : `当前权重合计 ${rows.reduce((sum, row) => sum + (row.weight ?? 0), 0)}；发布要求合计为1。`}{" "}
                参考区间必须有依据；不从预览样本极值生成。
              </p>
            ) : (
              <p>添加指标后配置赋权。</p>
            )}
            {config.weighting && rows.length ? (
              <AhpMatrix
                project={project}
                indicators={rows.map((row) => row.concept)}
                definition={config.weighting}
                change={(weighting) =>
                  change({
                    ...definition,
                    configuration: { ...config, weighting },
                  })
                }
              />
            ) : null}
          </>
        ) : (
          <>
            <div className="method-form-grid">
              <label>
                综合方式
                <select
                  value={config.weighting ? "ahp" : config.method}
                  onChange={(e) => {
                    const method = e.target.value;
                    if (method === "ahp") {
                      change({
                        ...definition,
                        configuration: {
                          task: "assessment",
                          method: "weighted",
                          indicators: rows.map((row) => ({
                            ...row,
                            weight: null,
                          })),
                          weighting: blankAhp(rows.map((row) => row.concept)),
                        },
                      });
                      return;
                    }
                    if (method === "binary_allocation") {
                      if (
                        rows.length &&
                        !window.confirm(
                          "切换为空间优化会替换本草稿的评价指标配置；已发布版本保持不变。继续？",
                        )
                      )
                        return;
                      change({
                        ...definition,
                        configuration: emptyOptimization,
                      });
                      return;
                    }
                    change({
                      ...definition,
                      configuration: {
                        ...(config.task === "assessment"
                          ? config
                          : { task: "assessment" }),
                        method,
                        weighting: null,
                        indicators: rows.map((row) => ({
                          ...row,
                          weight: method === "entropy" ? null : row.weight,
                        })),
                      },
                    });
                  }}
                >
                  <option value="weighted">明确权重加权综合</option>
                  <option value="ahp">AHP判断赋权综合</option>
                  <option value="entropy">熵权综合</option>
                  <option value="topsis">TOPSIS排序</option>
                  <option value="binary_allocation">空间布局优化</option>
                </select>
              </label>
            </div>
            <OptimizationRules
              configuration={config}
              change={(next) =>
                change({
                  ...definition,
                  configuration: {
                    ...next,
                    task: "optimization",
                    method: "binary_allocation",
                  },
                })
              }
            />
          </>
        )}
        <details
          id="method-basis"
          open={
            publicationIssues?.success &&
            publicationIssues.data.issues.some((i) => i.field === "basis")
          }
        >
          <summary>方案说明与依据</summary>
          <label className="method-basis">
            方法科学依据
            <textarea
              rows={2}
              value={definition.basis}
              onChange={(e) => change({ ...definition, basis: e.target.value })}
            />
          </label>
          <h3>适用资料</h3>
          <p>
            {definition.profiles.join("、")}
            。导入档案的适用范围原样保留，运行时重新核验。
          </p>
        </details>
        {publicationIssues?.success ? (
          <div role="alert">
            <p>{error instanceof Error ? error.message : "请核对方法"}</p>
            <ul>
              {publicationIssues.data.issues.map((issue, index) => (
                <li key={index}>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      const field = document.getElementById(
                        "method-" + issue.field,
                      );
                      if (field instanceof HTMLDetailsElement)
                        field.open = true;
                      field?.scrollIntoView({ block: "nearest" });
                      field
                        ?.querySelector<HTMLElement>(
                          "input,textarea,button,select",
                        )
                        ?.focus();
                    }}
                  >
                    {issue.message}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <ErrorNotice error={error} />
        )}
        {error instanceof APIError && error.status === 409 ? (
          <button
            type="button"
            className="secondary"
            onClick={() =>
              void api(`/method-workspaces/${value.id}`, workspaceSchema).then(
                (next) => {
                  current.current = next;
                  saved.current = next.definition;
                  setValue(next);
                  setError(null);
                  setStatus("已读取服务器版本");
                },
              )
            }
          >
            放弃本地未保存修改并读取最新版本
          </button>
        ) : null}
      </div>
    </section>
  );
}
