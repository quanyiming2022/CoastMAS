import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { ManagedCatalog, Modal, type CatalogRow } from "./ManagedCatalog";
import { ProjectSources, AuditLog } from "./ProjectGovernance";
import { ErrorNotice } from "./shared";
const roleNames = {
  viewer: "只读成员",
  analyst: "分析成员",
  curator: "资料维护者",
  manager: "项目负责人",
};
function ProjectMembers({
  row,
  close,
  onEnter,
}: {
  row: CatalogRow;
  close: () => void;
  onEnter: (id: string) => void;
}) {
  const [tab, setTab] = useState("members");
  const cache = useQueryClient();
  const [search, setSearch] = useState(""),
    [candidate, setCandidate] = useState(""),
    [role, setRole] = useState("viewer"),
    [error, setError] = useState<unknown>(null);
  const members = useQuery({
    queryKey: ["members", row.id],
    queryFn: () =>
      api(
        `/projects/${row.id}/members`,
        z.array(
          z.object({
            id: z.string(),
            email: z.string(),
            role: z.string(),
            active: z.boolean(),
          }),
        ),
      ),
  });
  const candidates = useQuery({
    queryKey: ["member-candidates", row.id, search],
    enabled: !!members.data,
    queryFn: () =>
      api(
        `/projects/${row.id}/member-candidates?search=${encodeURIComponent(search)}`,
        z.array(z.object({ id: z.string(), email: z.string() })),
      ),
  });
  async function change(id: string, value: string | null) {
    try {
      setError(null);
      await api(`/projects/${row.id}/members/${id}`, z.unknown(), {
        method: value ? "PUT" : "DELETE",
        ...(value ? { body: JSON.stringify({ role: value }) } : {}),
      });
      await cache.invalidateQueries({ queryKey: ["members", row.id] });
      await cache.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Modal title="项目详情与成员" close={close}>
      <h3>{row.name}</h3>
      <p>查看详情不会切换研究。项目角色不授予系统管理权限。</p>
      <button onClick={() => onEnter(row.id)}>进入项目</button>
      <div role="tablist" aria-label="项目详情栏目">
        {[
          ["basic", "基本信息"],
          ["members", "成员与权限"],
          ["sources", "数据源授权"],
          ["activity", "项目活动"],
        ].map(([key, label]) => (
          <button
            type="button"
            role="tab"
            aria-selected={tab === key}
            className="secondary"
            key={key}
            onClick={() => setTab(key!)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "basic" ? (
        <dl>
          <dt>项目名称</dt>
          <dd>{row.name}</dd>
          <dt>分类</dt>
          <dd>{row.classification || "未分类"}</dd>
          <dt>状态</dt>
          <dd>
            {row.state === "active"
              ? "活跃"
              : row.state === "archived"
                ? "已归档"
                : "已回收"}
          </dd>
        </dl>
      ) : null}
      {tab === "sources" ? <ProjectSources project={row.id} /> : null}
      {tab === "activity" ? <AuditLog project={row.id} /> : null}
      <div hidden={tab !== "members"}>
        <ErrorNotice error={members.error ?? error} />
        {members.data ? (
          <>
            <table>
              <thead>
                <tr>
                  <th>账号</th>
                  <th>项目角色</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {members.data.map((m) => (
                  <tr key={m.id}>
                    <td>{m.email}</td>
                    <td>
                      <select
                        aria-label={`${m.email} 项目角色`}
                        value={m.role}
                        onChange={(e) => void change(m.id, e.target.value)}
                      >
                        {Object.entries(roleNames).map(([v, n]) => (
                          <option key={v} value={v}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <button
                        className="secondary"
                        onClick={() => void change(m.id, null)}
                      >
                        移除成员
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (candidate) void change(candidate, role);
              }}
            >
              <label>
                搜索可加入账号
                <input
                  type="search"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </label>
              <label>
                选择账号
                <select
                  required
                  value={candidate}
                  onChange={(e) => setCandidate(e.target.value)}
                >
                  <option value="">请选择账号</option>
                  {candidates.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.email}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                项目角色
                <select value={role} onChange={(e) => setRole(e.target.value)}>
                  {Object.entries(roleNames).map(([v, n]) => (
                    <option key={v} value={v}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={!candidate}>加入项目</button>
            </form>
          </>
        ) : (
          <p>成员清单仅对该项目负责人开放。</p>
        )}
      </div>
    </Modal>
  );
}
export function ManagementCenter({
  kind,
  project,
  onEnter,
}: {
  kind: "users" | "projects";
  project: string;
  onEnter: (id: string) => void;
}) {
  const cache = useQueryClient();
  const [creating, setCreating] = useState(false),
    [detail, setDetail] = useState<CatalogRow | null>(null),
    [reset, setReset] = useState<CatalogRow | null>(null);
  const [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [admin, setAdmin] = useState(false),
    [visible, setVisible] = useState(false),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  function close() {
    setCreating(false);
    setReset(null);
    setPassword("");
    setError(null);
  }
  return (
    <>
      <h1>{kind === "users" ? "用户管理" : "项目管理"}</h1>
      <p>
        {kind === "users"
          ? "系统账号目录 · 创建账号不会自动加入任何项目。"
          : "项目与成员目录 · 查看和编辑项目不会改变当前研究。"}
      </p>
      <p role="status">{message}</p>
      <ManagedCatalog
        kind={kind}
        project={project}
        onNew={() => {
          setName("");
          setPassword("");
          setAdmin(false);
          setCreating(true);
        }}
        onOpen={kind === "projects" ? setDetail : undefined}
        extraActions={
          kind === "users"
            ? (row) => (
                <button
                  className="secondary"
                  onClick={() => {
                    setPassword("");
                    setReset(row);
                  }}
                >
                  重置密码
                </button>
              )
            : undefined
        }
      />
      {detail ? (
        <ProjectMembers
          row={detail}
          close={() => setDetail(null)}
          onEnter={onEnter}
        />
      ) : null}
      {creating || reset ? (
        <Modal
          title={
            reset ? "单独重置密码" : kind === "users" ? "创建账号" : "新建项目"
          }
          close={close}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                if (reset) {
                  await api(`/accounts/${reset.id}/password`, z.unknown(), {
                    method: "POST",
                    body: JSON.stringify({ password }),
                  });
                  setMessage("密码已重置，原会话已撤销。");
                } else {
                  await api(
                    kind === "users" ? "/accounts" : "/projects",
                    z.unknown(),
                    {
                      method: "POST",
                      body: JSON.stringify(
                        kind === "users"
                          ? { email: name, password, system_admin: admin }
                          : { name },
                      ),
                    },
                  );
                  setMessage("创建成功。研究现场保持不变。");
                }
                close();
                await cache.invalidateQueries({
                  queryKey: ["managed-catalog"],
                });
                await cache.invalidateQueries({ queryKey: ["projects"] });
              } catch (e) {
                setError(e);
              } finally {
                setBusy(false);
              }
            }}
          >
            {reset ? (
              <p>
                账号：{reset.name}
                。此操作撤销该账号现有会话，密码只用于本次提交。
              </p>
            ) : (
              <label>
                {kind === "users" ? "邮箱" : "项目名称"}
                <input
                  required
                  type={kind === "users" ? "email" : "text"}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            {kind === "users" || reset ? (
              <>
                <label>
                  新密码
                  <input
                    required
                    minLength={12}
                    type={visible ? "text" : "password"}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={visible}
                    onChange={(e) => setVisible(e.target.checked)}
                  />
                  显示密码
                </label>
              </>
            ) : null}
            {kind === "users" && !reset ? (
              <label>
                <input
                  type="checkbox"
                  checked={admin}
                  onChange={(e) => setAdmin(e.target.checked)}
                />
                授予系统管理员（不授予项目科学资料权限）
              </label>
            ) : null}
            <ErrorNotice error={error} />
            <button disabled={busy}>{reset ? "确认重置" : "创建"}</button>
          </form>
        </Modal>
      ) : null}
    </>
  );
}
