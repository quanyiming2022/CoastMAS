import { runLabels } from "./shared";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { ErrorNotice, purposes } from "./shared";
import { useCatalogSearch } from "./catalogSearch";
export type CatalogKind =
  "users" | "projects" | "tasks" | "methods" | "runs" | "results";
const rowSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    revision: z.number(),
    state: z.string(),
    classification: z.string(),
    status: z.string(),
    updated: z.number(),
  })
  .passthrough();
export type CatalogRow = z.infer<typeof rowSchema>;
const pageSchema = z.object({ items: z.array(rowSchema), total: z.number() });
const planSchema = z.object({
  id: z.string(),
  count: z.number(),
  items: z.array(z.object({ id: z.string(), name: z.string() })),
  impact: z.string(),
  action: z.string(),
});
const resultSchema = z.object({
  succeeded: z.number(),
  failed: z.number(),
  items: z.array(
    z.object({
      id: z.string(),
      status: z.string(),
      message: z.string().optional(),
    }),
  ),
});
export function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className="catalog-modal"
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
    >
      <div className="section-heading">
        <h2>{title}</h2>
        <button type="button" className="secondary" onClick={close}>
          关闭
        </button>
      </div>
      {children}
    </dialog>
  );
}
function PageSelect({
  disabled,
  checked,
  partial,
  change,
}: {
  disabled: boolean;
  checked: boolean;
  partial: boolean;
  change: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <input
      ref={(el) => {
        ref.current = el;
        if (el) el.indeterminate = partial;
      }}
      type="checkbox"
      disabled={disabled}
      aria-label="全选本页"
      checked={checked}
      onChange={change}
    />
  );
}
export function ManagedCatalog({
  kind,
  project,
  onOpen,
  onNew,
  extraActions,
  toolbarExtras,
  active = true,
  fixedStatus,
  title: suppliedTitle,
}: {
  kind: CatalogKind;
  fixedStatus?: string;
  title?: string;
  active?: boolean;
  project: string;
  onOpen?: (row: CatalogRow) => void;
  onNew?: () => void;
  extraActions?: (row: CatalogRow) => ReactNode;
  toolbarExtras?: ReactNode;
}) {
  const cache = useQueryClient(),
    search = useCatalogSearch();
  const [offset, setOffset] = useState(0),
    [limit, setLimit] = useState(25),
    [sort, setSort] = useState("updated"),
    [state, setState] = useState("active"),
    [status, setStatus] = useState("");
  const [selected, setSelected] = useState<string[]>([]),
    [plan, setPlan] = useState<z.infer<typeof planSchema> | null>(null),
    [confirm, setConfirm] = useState(false);
  const [edit, setEdit] = useState<CatalogRow | null>(null),
    [name, setName] = useState(""),
    [classification, setClassification] = useState(""),
    [systemAdmin, setSystemAdmin] = useState(false);
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [outcome, setOutcome] = useState<z.infer<typeof resultSchema> | null>(null);
  const filter = { query: search.query, state, sort, status: fixedStatus ?? status };
  const params = new URLSearchParams({
    ...filter,
    project,
    offset: String(offset),
    limit: String(limit),
  });
  const root = `/management/catalog/${kind}`;
  const listing = useQuery({
    enabled: active,
    queryKey: ["managed-catalog", kind, project, params.toString()],
    queryFn: () => api(`${root}?${params}`, pageSchema),
  });
  const rows = listing.data?.items ?? [];
  const selectionReady =
    search.text.trim() === search.query &&
    !listing.isFetching &&
    !!listing.data &&
    !listing.error;
  const title = suppliedTitle ?? {
    users: "用户管理",
    projects: "项目管理",
    tasks: "任务管理",
    methods: "方法方案",
    runs: "运行记录",
    results: "成果管理",
  }[kind];
  async function refresh() {
    await cache.invalidateQueries({ queryKey: ["managed-catalog"] });
    await cache.invalidateQueries({ queryKey: ["projects"] });
    await cache.invalidateQueries({ queryKey: ["task"] });
  }
  function changed() {
    setOffset(0);
    setSelected([]);
    setPlan(null);
  }
  async function freeze(action: string, all = false) {
    setBusy(true);
    setError(null);
    try {
      const value = await api(
        `${root}/selections?project=${project}`,
        planSchema,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            ...(all ? { query: filter } : { ids: selected }),
          }),
        },
      );
      setPlan(value);
      if (!all) setConfirm(true);
      setSelected(value.items.map((r) => r.id));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (!plan) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api(
        `/management/selections/${plan.id}/apply`,
        resultSchema,
        { method: "POST" },
      );
      setOutcome(result);
      setSelected(
        result.items.filter((r) => r.status === "failed").map((r) => r.id),
      );
      setPlan(null);
      setConfirm(false);
      await refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function openEdit(row: CatalogRow) {
    setEdit(row);
    setName(row.name);
    setClassification(row.classification);
    setSystemAdmin(row.system_admin === true);
  }
  return (
    <section className="managed-catalog" aria-label={title}>
      <div className="catalog-toolbar">
        <h2>{title}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            search.submit();
            changed();
          }}
        >
          <input
            aria-label={`搜索${title}`}
            type="search"
            placeholder="搜索全部授权记录"
            value={search.text}
            onChange={(e) => {
              search.change(e.target.value);
              changed();
            }}
            onCompositionStart={() => search.compose(true)}
            onCompositionEnd={() => search.compose(false)}
          />
        </form>
        <select
          aria-label="目录状态"
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            changed();
          }}
        >
          <option value="active">正常记录</option>
          <option value="archived">已归档</option>
          <option value="recycled">回收站</option>
          <option value="all">全部状态</option>
        </select>
        <select
          aria-label="业务状态"
          disabled={!!fixedStatus}
          value={fixedStatus ?? status}
          onChange={(e) => {
            setStatus(e.target.value);
            changed();
          }}
        >
          <option value="">全部类型/状态</option>
          {(kind === "users"
            ? Object.entries({
                active: "有效账号",
                disabled: "停用账号",
                admin: "系统管理员",
              })
            : kind === "tasks"
              ? Object.entries(purposes)
              : kind === "methods"
                ? Object.entries({ approved: "已认可", draft: "待认可" })
                : kind === "runs" || kind === "results"
                  ? Object.entries({
                      queued: "排队中",
                      running: "计算中",
                      succeeded: "计算完成",
                      failed: "失败",
                      cancelled: "已取消",
                    })
                  : []
          ).map(([v, n]) => (
            <option key={v} value={v}>
              {n}
            </option>
          ))}
        </select>
        <select
          aria-label="目录排序"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            changed();
          }}
        >
          <option value="updated">最近更新</option>
          <option value="name">名称</option>
        </select>
        <button
          type="button"
          className="secondary"
          onClick={() => void refresh()}
        >
          刷新
        </button>
        {toolbarExtras}
        {onNew ? (
          <button type="button" onClick={onNew}>
            新建
          </button>
        ) : null}
      </div>
      <ErrorNotice error={error ?? listing.error} />
      <div className="catalog-bulk">
        <span>
          已选 {selected.length} 项{plan ? " · 已冻结筛选选集" : ""}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={busy || !selectionReady || !listing.data?.total}
          onClick={() =>
            void freeze(
              ["recycled", "archived"].includes(state) ? "restore" : "recycle",
              true,
            )
          }
        >
          全选筛选结果
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!selected.length}
          onClick={() => {
            setSelected([]);
            setPlan(null);
          }}
        >
          清除选择
        </button>
        {(["recycled", "archived"].includes(state)
          ? ["restore"]
          : kind === "users"
            ? ["disable", "enable", "recycle"]
            : ["archive", "recycle"]
        ).map((action) => (
          <button
            key={action}
            type="button"
            className="secondary"
            disabled={busy || !selectionReady || !selected.length}
            onClick={() => {
              if (plan?.action === action) setConfirm(true);
              else void freeze(action);
            }}
          >
            {
              {
                restore: "恢复",
                archive: "归档",
                recycle: "移入回收站",
                disable: "停用",
                enable: "启用",
              }[action]
            }
          </button>
        ))}
      </div>
      {outcome ? (
        <div role="status">
          成功 {outcome.succeeded} 项，失败 {outcome.failed} 项。
          {outcome.items
            .filter((i) => i.status === "failed")
            .map((i) => (
              <p key={i.id}>{i.message}</p>
            ))}
        </div>
      ) : null}
      {listing.isPending ? (
        <p role="status">正在读取目录…</p>
      ) : listing.error ? (
        <button onClick={() => void listing.refetch()}>重新读取</button>
      ) : !rows.length ? (
        <p>{search.query ? "没有匹配的记录" : "此分类暂无记录"}</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>
                  <PageSelect
                    disabled={!selectionReady}
                    checked={rows.every((r) => selected.includes(r.id))}
                    partial={
                      rows.some((r) => selected.includes(r.id)) &&
                      !rows.every((r) => selected.includes(r.id))
                    }
                    change={() => {
                      setPlan(null);
                      setSelected(
                        rows.every((r) => selected.includes(r.id))
                          ? selected.filter(
                              (id) => !rows.some((r) => r.id === id),
                            )
                          : [
                              ...new Set([
                                ...selected,
                                ...rows.map((r) => r.id),
                              ]),
                            ],
                      );
                    }}
                  />
                </th>
                <th>名称</th>
                <th>
                  {kind === "users"
                    ? "系统身份"
                    : kind === "tasks"
                      ? "研究类型"
                      : kind === "methods"
                        ? "算法"
                        : "分类"}
                </th>
                <th>状态</th>
                {kind === "tasks" ? (
                  <>
                    <th>当前环节</th>
                    <th>最近运行 / 成果</th>
                  </>
                ) : kind === "methods" ? (
                  <>
                    <th>指标数</th>
                    <th>固定版本</th>
                  </>
                ) : kind === "users" || kind === "projects" ? (
                  <th>{kind === "users" ? "项目关联" : "成员数"}</th>
                ) : (
                  <th>配置版本</th>
                )}
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} aria-selected={selected.includes(row.id)}>
                  <td>
                    <input
                      type="checkbox"
                      disabled={!selectionReady}
                      aria-label={`选择 ${row.name}`}
                      checked={selected.includes(row.id)}
                      onChange={() => {
                        setPlan(null);
                        setSelected(
                          selected.includes(row.id)
                            ? selected.filter((id) => id !== row.id)
                            : [...selected, row.id],
                        );
                      }}
                    />
                  </td>
                  <td className="catalog-name" title={row.name}>
                    {row.name}
                  </td>
                  <td>
                    {kind === "users"
                      ? row.system_admin
                        ? "系统管理员"
                        : "普通账号"
                      : kind === "tasks"
                        ? (purposes[
                            String(row.purpose) as keyof typeof purposes
                          ] ?? String(row.purpose))
                        : kind === "methods"
                          ? ((
                              {
                                weighted: "固定权重综合",
                                entropy: "熵权综合",
                                topsis: "TOPSIS贴近度",
                                binary_allocation: "空间布局优化",
                              } as Record<string, string>
                            )[String(row.algorithm)] ?? String(row.algorithm))
                          : row.classification || "未分类"}
                  </td>
                  <td>
                    {(
                      {
                        active: "正常",
                        disabled: "停用",
                        approved: "已认可",
                        draft: "待认可",
                        succeeded: "计算完成",
                        running: "运行中",
                        queued: "排队中",
                        failed: "失败",
                        cancelled: "已取消",
                        recycled: "已回收",
                        archived: "已归档",
                      } as Record<string, string>
                    )[row.state === "active" ? row.status : row.state] ??
                      row.status}
                  </td>
                  {kind === "tasks" ? (
                    <>
                      <td>{String(row.stage)}</td>
                      <td>
                        {row.last_run
                          ? (runLabels[
                              (row.last_run as { status: string }).status
                            ] ?? "状态待确认")
                          : "暂无运行"}
                      </td>
                    </>
                  ) : kind === "methods" ? (
                    <>
                      <td>{String(row.indicator_count)}</td>
                      <td>v{String(row.source_revision)}</td>
                    </>
                  ) : kind === "users" || kind === "projects" ? (
                    <td>
                      {String(row.project_count ?? row.member_count ?? "未知")}
                    </td>
                  ) : (
                    <td>v{String(row.source_revision ?? "—")}</td>
                  )}
                  <td className="catalog-actions">
                    {onOpen ? (
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => onOpen(row)}
                      >
                        {kind === "tasks"
                          ? "继续任务"
                          : kind === "methods"
                            ? "查看方法"
                            : kind === "projects"
                              ? "详情与成员"
                              : kind === "runs" || kind === "results"
                                ? "查看成果"
                                : "详情"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => openEdit(row)}
                    >
                      编辑
                    </button>
                    {extraActions?.(row)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination">
        <span>
          共 {listing.data?.total ?? "…"} 项 · 第{" "}
          {Math.floor(offset / limit) + 1} 页
        </span>
        <select
          aria-label="每页数量"
          value={limit}
          onChange={(e) => {
            setLimit(Number(e.target.value));
            setOffset(0);
          }}
        >
          {[25, 50, 100].map((n) => (
            <option key={n} value={n}>
              {n} 项/页
            </option>
          ))}
        </select>
        <button
          className="secondary"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - limit))}
        >
          上一页
        </button>
        <button
          className="secondary"
          disabled={!listing.data || offset + limit >= listing.data.total}
          onClick={() => setOffset(offset + limit)}
        >
          下一页
        </button>
      </div>
      {confirm && plan ? (
        <Modal title="确认目录操作" close={() => setConfirm(false)}>
          <p>
            {plan.count} 项 · {plan.impact}
          </p>
          <ul>
            {plan.items.slice(0, 20).map((r) => (
              <li key={r.id}>{r.name}</li>
            ))}
          </ul>
          <button disabled={busy} onClick={() => void apply()}>
            确认执行
          </button>
        </Modal>
      ) : null}
      {edit ? (
        <Modal title="编辑管理信息" close={() => setEdit(null)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await api(`${root}/${edit.id}`, rowSchema, {
                  method: "PATCH",
                  body: JSON.stringify({
                    expected_revision: edit.revision,
                    changes: {
                      classification,
                      ...(kind === "users"
                        ? {
                            email: name,
                            ...(systemAdmin !== edit.system_admin
                              ? { system_admin: systemAdmin }
                              : {}),
                          }
                        : ["projects", "tasks", "results"].includes(kind)
                          ? { name }
                          : {}),
                    },
                  }),
                });
                setEdit(null);
                await refresh();
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {["users", "projects", "tasks", "results"].includes(kind) ? (
              <label>
                {kind === "users" ? "邮箱" : "名称"}
                <input
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            ) : (
              <p>{edit.name} · 科学定义和历史数值不在此修改</p>
            )}
            <label>
              管理分类
              <input
                value={classification}
                onChange={(e) => setClassification(e.target.value)}
              />
            </label>
            {kind === "users" ? (
              <label>
                <input
                  type="checkbox"
                  checked={systemAdmin}
                  onChange={(e) => setSystemAdmin(e.target.checked)}
                />
                系统管理员（仅管理系统，不自动加入项目）
              </label>
            ) : null}
            <ErrorNotice error={error} />
            <button disabled={busy}>保存修改</button>
          </form>
        </Modal>
      ) : null}
    </section>
  );
}
