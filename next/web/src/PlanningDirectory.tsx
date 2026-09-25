import { useEffect, useState, useSyncExternalStore } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError } from "./api";
import { Modal } from "./ManagedCatalog";
import { ErrorNotice } from "./shared";
import {
  PlanningDraftSession,
  PlanningConflict,
  planningObjectSchema,
  type PlanningObject,
  type PlanningBody,
  type PlanningKind,
} from "./planningDraft";

const recipe = z.object({
  code: z.string(),
  name: z.string(),
  description: z.string().optional(),
  direction: z.string().optional(),
  action: z.string().optional(),
  limit_required: z.boolean().optional(),
});
const catalogSchema = z.object({
  version: z.string(),
  objectives: z.array(recipe),
  constraints: z.array(recipe),
  decisions: z.array(recipe),
  limitations: z.array(z.string()),
});
const listSchema = z.object({
  items: z.array(planningObjectSchema),
  total: z.number(),
  can_edit: z.boolean(),
});
const names = {
  objectives: "规划目标",
  constraints: "约束库",
  decisions: "决策变量",
};
const path = (project: string, kind: PlanningKind) =>
  `/v1/projects/${project}/planning/${kind}`;
export type PlanningReference = {
  kind: PlanningKind;
  object_id: string;
  version_id: string;
};

export function PlanningDirectory({
  project,
  kind,
  onApply,
}: {
  project: string;
  kind: PlanningKind;
  onApply?: (ref: PlanningReference) => Promise<void>;
}) {
  const [search, setSearch] = useState(""),
    [offset, setOffset] = useState(0),
    [sort, setSort] = useState("updated");
  const [editor, setEditor] = useState<PlanningObject | null>(null),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["planning-directory", project, kind, search, sort, offset],
    queryFn: () =>
      api(
        `${path(project, kind)}?search=${encodeURIComponent(search)}&sort=${sort}&offset=${offset}&limit=25`,
        listSchema,
      ),
  });
  const recipes = useQuery({
    queryKey: ["planning-recipes", project],
    queryFn: () =>
      api(`/v1/projects/${project}/planning-catalog`, catalogSchema),
  });
  async function create() {
    setBusy(true);
    setError(null);
    try {
      const value = await api(path(project, kind), planningObjectSchema, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setCreating(false);
      setEditor(value);
      await query.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="domain-directory planning-directory"
      aria-label={names[kind]}
    >
      <div className="planning-toolbar">
        <h2>{names[kind]}</h2>
        <input
          aria-label={`搜索${names[kind]}`}
          placeholder="搜索名称"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label="排序"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setOffset(0);
          }}
        >
          <option value="updated">最近更新</option>
          <option value="name">名称</option>
        </select>
        <button type="button" onClick={() => void query.refetch()}>
          刷新
        </button>
        {query.data?.can_edit ? (
          <button
            type="button"
            className="primary"
            onClick={() => {
              setName("");
              setCreating(true);
            }}
          >
            新建{names[kind]}
          </button>
        ) : null}
      </div>
      <ErrorNotice error={query.error ?? recipes.error ?? error} />
      {query.isPending ? (
        <p role="status">正在读取…</p>
      ) : query.data?.items.length === 0 ? (
        <p>
          {search
            ? "没有匹配记录"
            : `尚无${names[kind]}。可独立创建，发布后供规划任务复用。`}
        </p>
      ) : null}
      {query.data?.items.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>草稿</th>
                <th>已发布配置</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.name}</td>
                  <td>v{item.revision}</td>
                  <td>
                    {item.versions.length
                      ? `共 ${item.versions.length} 个固定版本`
                      : "未发布"}
                  </td>
                  <td>
                    <button
                      type="button"
                      disabled={!recipes.data}
                      onClick={() => setEditor(item)}
                    >
                      {query.data.can_edit ? "编辑 / 查看版本" : "查看"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {query.data ? (
        <footer className="planning-pagination">
          <span>
            共 {query.data.total} 项 · 第 {Math.floor(offset / 25) + 1} 页
          </span>
          <button
            type="button"
            disabled={!offset}
            onClick={() => setOffset(offset - 25)}
          >
            上一页
          </button>
          <button
            type="button"
            disabled={offset + 25 >= query.data.total}
            onClick={() => setOffset(offset + 25)}
          >
            下一页
          </button>
        </footer>
      ) : null}
      {creating ? (
        <Modal title={`新建${names[kind]}`} close={() => setCreating(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void create();
            }}
          >
            <label>
              名称
              <input
                autoFocus
                required
                maxLength={240}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <ErrorNotice error={error} />
            <button disabled={busy} className="primary">
              创建草稿
            </button>
          </form>
        </Modal>
      ) : null}
      {editor && recipes.data ? (
        <PlanningEditor
          key={editor.id}
          initial={editor}
          recipes={recipes.data}
          canEdit={query.data?.can_edit ?? false}
          onApply={onApply}
          close={() => {
            setEditor(null);
            void query.refetch();
          }}
        />
      ) : null}
    </section>
  );
}

function PlanningEditor({
  initial,
  recipes,
  canEdit,
  onApply,
  close,
}: {
  initial: PlanningObject;
  recipes: z.infer<typeof catalogSchema>;
  canEdit: boolean;
  onApply?: (ref: PlanningReference) => Promise<void>;
  close: () => void;
}) {
  const url = path(initial.project_id, initial.kind) + "/" + initial.id;
  const [session] = useState(
    () =>
      new PlanningDraftSession(initial, async (value) => {
        try {
          return await api(url, planningObjectSchema, {
            method: "PUT",
            headers: { "If-Match": `"${value.revision}"` },
            body: JSON.stringify({ name: value.name, body: value.body }),
          });
        } catch (error) {
          if (error instanceof APIError && error.status === 412) {
            const detail = z
              .object({ current: planningObjectSchema })
              .safeParse(error.details);
            if (detail.success) throw new PlanningConflict(detail.data.current);
          }
          throw error;
        }
      }),
  );
  const snapshot = useSyncExternalStore(session.subscribe, session.snapshot),
    value = snapshot.value,
    body = value.body;
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [viewed, setViewed] = useState<{
      name: string;
      body: PlanningBody;
      version: number;
    } | null>(null),
    [message, setMessage] = useState("");
  useEffect(() => {
    if (snapshot.status !== "unsaved") return;
    const timer = setTimeout(() => {
      void session.save().catch(() => {});
    }, 350);
    return () => clearTimeout(timer);
  }, [session, snapshot.status, snapshot.value]);
  useEffect(() => {
    const guard = (e: BeforeUnloadEvent) => {
      if (session.snapshot().status !== "saved") {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [session]);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      await session.save();
      await fn();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const edit = (next: PlanningBody) => session.edit({ body: next });
  const labels = Object.fromEntries(
    [...recipes.objectives, ...recipes.constraints, ...recipes.decisions].map(
      (r) => [r.code, r.name],
    ),
  );
  const summary = (value: PlanningObject) =>
    [
      value.name,
      value.body.mode === "pareto_multiobjective"
        ? "多目标权衡"
        : value.body.mode === "weighted_multiobjective"
          ? "加权多目标"
          : value.body.mode
            ? "单目标"
            : "",
      ...(value.body.items ?? []).map(
        (i) =>
          `${labels[i.metric ?? i.recipe ?? ""] ?? ""}${i.weight !== undefined ? " · 权重 " + i.weight : ""}${i.limit !== undefined ? " · 上限 " + i.limit + " " + i.unit : ""}${i.basis ? " · 依据 " + i.basis : ""}`,
      ),
      labels[value.body.template ?? ""] ?? "",
    ]
      .filter(Boolean)
      .join("；");
  return (
    <Modal
      title={names[initial.kind] + " · " + initial.name}
      close={() => void action(async () => close())}
    >
      <div className="planning-editor">
        <div className="planning-toolbar">
          <span role="status">
            {snapshot.status === "saved"
              ? "已保存"
              : snapshot.status === "saving"
                ? "保存中…"
                : snapshot.status === "conflict"
                  ? "存在冲突"
                  : snapshot.status === "error"
                    ? "保存失败"
                    : "尚未保存"}
          </span>
          <span>草稿 v{value.revision}</span>
          {canEdit ? (
            <button
              type="button"
              disabled={busy || snapshot.status === "conflict"}
              onClick={() => void action(async () => {})}
            >
              保存
            </button>
          ) : null}
        </div>
        <ErrorNotice error={snapshot.error ?? error} />
        {snapshot.remote ? (
          <section aria-label="版本冲突对比">
            <h3>请核对双方修改</h3>
            <dl>
              <dt>编辑前</dt>
              <dd>{summary(snapshot.base)}</dd>
              <dt>服务器当前</dt>
              <dd>{summary(snapshot.remote)}</dd>
              <dt>我的修改</dt>
              <dd>{summary(value)}</dd>
            </dl>
            <button type="button" onClick={() => session.useRemote()}>
              采用服务器版本
            </button>
            <button type="button" onClick={() => session.keepLocal()}>
              保留我的修改并重新保存
            </button>
          </section>
        ) : null}
        <fieldset disabled={!canEdit || busy || !!snapshot.remote}>
          <legend>当前草稿</legend>
          <label>
            名称
            <input
              maxLength={240}
              value={value.name}
              onChange={(e) => session.edit({ name: e.target.value })}
            />
          </label>
          {initial.kind === "objectives" ? (
            <>
              <label>
                目标组织方式
                <select
                  value={body.mode}
                  onChange={(e) =>
                    edit({
                      ...body,
                      mode: e.target.value as PlanningBody["mode"],
                      items: (body.items ?? []).map((i) => ({
                        metric: i.metric,
                      })),
                    })
                  }
                >
                  <option value="single_objective">单目标</option>
                  <option value="weighted_multiobjective">加权多目标</option>
                  <option value="pareto_multiobjective">
                    多目标权衡（不预设权重）
                  </option>
                </select>
              </label>
              <div className="planning-choices">
                {recipes.objectives.map((r) => {
                  const selected = (body.items ?? []).find(
                    (i) => i.metric === r.code,
                  );
                  return (
                    <label key={r.code}>
                      <input
                        type="checkbox"
                        checked={!!selected}
                        onChange={(e) =>
                          edit({
                            ...body,
                            items: e.target.checked
                              ? [...(body.items ?? []), { metric: r.code }]
                              : (body.items ?? []).filter(
                                  (i) => i.metric !== r.code,
                                ),
                          })
                        }
                      />
                      {r.name}
                    </label>
                  );
                })}
              </div>
              {body.mode === "weighted_multiobjective"
                ? (body.items ?? []).map((item, index) => (
                    <label key={item.metric}>
                      {labels[item.metric ?? ""]}权重
                      <input
                        type="number"
                        min={0}
                        max={1}
                        step="any"
                        value={item.weight ?? ""}
                        onChange={(e) =>
                          edit({
                            ...body,
                            items: body.items?.map((i, j) =>
                              j === index
                                ? {
                                    metric: i.metric,
                                    ...(e.target.value !== ""
                                      ? { weight: Number(e.target.value) }
                                      : {}),
                                  }
                                : i,
                            ),
                          })
                        }
                      />
                    </label>
                  ))
                : null}
            </>
          ) : null}
          {initial.kind === "constraints" ? (
            <>
              <label>
                添加业务约束
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value)
                      edit({
                        ...body,
                        items: [
                          ...(body.items ?? []),
                          {
                            recipe: e.target.value,
                            basis: "",
                            ...(e.target.value === "development_quota"
                              ? { unit: "m^2" }
                              : {}),
                          },
                        ],
                      });
                  }}
                >
                  <option value="">选择约束</option>
                  {recipes.constraints.map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
              {(body.items ?? []).map((item, index) => {
                const definition = recipes.constraints.find(
                  (r) => r.code === item.recipe,
                );
                const change = (patch: Partial<typeof item>) =>
                  edit({
                    ...body,
                    items: body.items?.map((i, j) =>
                      j === index ? { ...i, ...patch } : i,
                    ),
                  });
                return (
                  <fieldset key={index}>
                    <legend>{labels[item.recipe ?? ""]}</legend>
                    {definition?.limit_required ? (
                      <div className="planning-fields">
                        <label>
                          上限
                          <input
                            type="number"
                            min={0}
                            step="any"
                            value={item.limit ?? ""}
                            onChange={(e) =>
                              change({
                                limit:
                                  e.target.value === ""
                                    ? undefined
                                    : Number(e.target.value),
                              })
                            }
                          />
                        </label>
                        <label>
                          单位
                          {item.recipe === "development_quota" ? (
                            <select
                              value={item.unit}
                              onChange={(e) => change({ unit: e.target.value })}
                            >
                              <option value="m^2">平方米</option>
                              <option value="ha">公顷</option>
                              <option value="km^2">平方千米</option>
                            </select>
                          ) : (
                            <input
                              value={item.unit ?? ""}
                              placeholder="资料声明的货币单位"
                              onChange={(e) => change({ unit: e.target.value })}
                            />
                          )}
                        </label>
                      </div>
                    ) : null}
                    <label>
                      适用依据
                      <textarea
                        rows={2}
                        value={item.basis}
                        onChange={(e) => change({ basis: e.target.value })}
                      />
                    </label>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() =>
                        edit({
                          ...body,
                          items: body.items?.filter((_, i) => i !== index),
                        })
                      }
                    >
                      移除此约束
                    </button>
                  </fieldset>
                );
              })}
            </>
          ) : null}
          {initial.kind === "decisions" ? (
            <>
              <label>
                允许优化器改变什么
                <select
                  value={body.template ?? ""}
                  onChange={(e) => {
                    const item = recipes.decisions.find(
                      (r) => r.code === e.target.value,
                    );
                    edit({
                      template: e.target.value,
                      actions: item?.action ? [item.action] : [],
                    });
                  }}
                >
                  <option value="">选择决策模板</option>
                  {recipes.decisions.map((r) => (
                    <option value={r.code} key={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </label>
              <p>
                {
                  recipes.decisions.find((r) => r.code === body.template)
                    ?.description
                }
              </p>
            </>
          ) : null}
        </fieldset>
        {canEdit ? (
          <button
            type="button"
            className="primary"
            disabled={busy || snapshot.status === "conflict"}
            onClick={() =>
              void action(async () => {
                await api(url + "/versions", z.unknown(), {
                  method: "POST",
                  headers: {
                    "If-Match": `"${session.snapshot().value.revision}"`,
                  },
                });
                session.replace(await api(url, planningObjectSchema));
                setMessage(
                  "已发布固定配置；尚未应用到研究，也不代表求解或业务批准。",
                );
              })
            }
          >
            发布配置版本
          </button>
        ) : null}
        {message ? <p role="status">{message}</p> : null}
        <h3>固定版本</h3>
        {value.versions.length === 0 ? (
          <p>尚未发布</p>
        ) : (
          <ul className="planning-version-list">
            {value.versions.map((v) => (
              <li key={v.id}>
                <span>
                  v{v.version} · {v.name}
                </span>
                <button
                  type="button"
                  onClick={() =>
                    void action(async () =>
                      setViewed(
                        await api(
                          url + "/versions/" + v.id,
                          z.object({
                            name: z.string(),
                            body: planningObjectSchema.shape.body,
                            version: z.number(),
                          }),
                        ),
                      ),
                    )
                  }
                >
                  查看配置
                </button>
                {onApply ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        await onApply({
                          kind: initial.kind,
                          object_id: initial.id,
                          version_id: v.id,
                        });
                        setMessage(
                          `已将固定版本 v${v.version} 应用到当前规划研究。`,
                        );
                      })
                    }
                  >
                    应用此版本
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
        {viewed ? (
          <aside aria-label="固定配置详情">
            <h3>
              v{viewed.version} · {viewed.name}
            </h3>
            <p>{summary({ ...value, ...viewed })}</p>
            <button type="button" onClick={() => setViewed(null)}>
              关闭版本详情
            </button>
          </aside>
        ) : null}
        <details>
          <summary>适用范围</summary>
          {recipes.limitations.map((x) => (
            <p key={x}>{x}</p>
          ))}
        </details>
      </div>
    </Modal>
  );
}
