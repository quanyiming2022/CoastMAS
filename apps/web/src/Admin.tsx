import { DataTable } from "./components";
import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request, projectSchema } from "./api";
import { Details, ErrorNotice, Loading, PageTitle, Panel } from "./components";

const accountSchema = z.object({
  id: z.string(),
  email: z.string(),
  active: z.boolean(),
  is_admin: z.boolean(),
});
const managedProject = projectSchema.extend({ archived: z.boolean() });
const memberSchema = z.object({
  user_id: z.string(),
  email: z.string(),
  role: z.string(),
  active: z.boolean(),
});
const auditSchema = z.object({
  id: z.string(),
  who: z.string(),
  when: z.string(),
  action: z.string(),
  resource: z.string(),
  old_value: z.unknown(),
  new_value: z.unknown(),
});
const roleLabels: Record<string, string> = {
  ADMIN: "管理员",
  RESEARCHER: "研究人员",
  MANAGER: "管理人员",
  VIEWER: "只读成员",
  PUBLIC: "公开参与者",
};
const auditLabels: Record<string, string> = {
  CREATE_USER: "创建账号",
  UPDATE_USER: "更新账号",
  SET_MEMBER: "设置项目角色",
  CREATE_PROJECT: "创建项目",
  ARCHIVE_PROJECT: "归档或恢复项目",
  CREATE_RESOURCE: "创建资源",
  UPDATE_RESOURCE: "修订资源",
  ARCHIVE_RESOURCE: "归档资源",
  QUARANTINE_SCIENTIFIC_DEMO: "隔离异常科学示范",
};

export default function Admin({ userId }: { userId: string }) {
  const client = useQueryClient();
  const [page, setPage] = useState(0);
  const [auditPage, setAuditPage] = useState(0);
  const [selected, setSelected] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [projectName, setProjectName] = useState("");
  const [member, setMember] = useState("");
  const [role, setRole] = useState("VIEWER");
  const [resetUser, setResetUser] = useState("");
  const [resetPassword, setResetPassword] = useState("");
  const users = useQuery({
    queryKey: ["admin-users", page],
    queryFn: ({ signal }) =>
      request(
        `/admin/users?limit=50&offset=${page * 50}`,
        z.array(accountSchema),
        { signal },
      ),
  });
  const projects = useQuery({
    queryKey: ["admin-projects"],
    queryFn: ({ signal }) =>
      request("/projects?include_archived=true", z.array(managedProject), {
        signal,
      }),
  });
  const project =
    projects.data?.find((item) => item.id === selected) ?? projects.data?.[0];
  const members = useQuery({
    queryKey: ["admin-members", project?.id],
    enabled: !!project,
    queryFn: ({ signal }) =>
      request(
        `/projects/${encodeURIComponent(project!.id)}/members`,
        z.array(memberSchema),
        { signal },
      ),
  });
  const audit = useQuery({
    queryKey: ["admin-audit", auditPage],
    queryFn: ({ signal }) =>
      request(
        `/admin/audit?limit=50&offset=${auditPage * 50}`,
        z.array(auditSchema),
        { signal },
      ),
  });
  async function refresh() {
    await Promise.all(
      [
        "admin-users",
        "admin-projects",
        "admin-members",
        "admin-audit",
        "projects",
      ].map((key) => client.invalidateQueries({ queryKey: [key] })),
    );
  }
  const change = useMutation({
    mutationFn: ({
      id,
      values,
    }: {
      id: string;
      values: { active?: boolean; is_admin?: boolean; password?: string };
    }) =>
      request(`/admin/users/${encodeURIComponent(id)}`, accountSchema, {
        method: "PATCH",
        body: values,
      }),
    onSuccess: async () => {
      setResetPassword("");
      await refresh();
    },
  });
  const createUser = useMutation({
    mutationFn: () =>
      request("/admin/users", accountSchema, {
        method: "POST",
        body: { email, password },
      }),
    onSuccess: async () => {
      setEmail("");
      setPassword("");
      await refresh();
    },
  });
  const createProject = useMutation({
    mutationFn: () =>
      request("/projects", projectSchema, {
        method: "POST",
        body: { name: projectName },
      }),
    onSuccess: async () => {
      setProjectName("");
      await refresh();
    },
  });
  const archive = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      request(`/projects/${encodeURIComponent(id)}/archive`, managedProject, {
        method: "POST",
        body: { archived },
      }),
    onSuccess: refresh,
  });
  const saveMember = useMutation({
    mutationFn: () =>
      request(
        `/projects/${encodeURIComponent(project!.id)}/members/${encodeURIComponent(member)}`,
        z.object({
          project_id: z.string(),
          user_id: z.string(),
          role: z.string(),
        }),
        { method: "PUT", body: { role } },
      ),
    onSuccess: refresh,
  });
  function submit(event: FormEvent, action: () => void) {
    event.preventDefault();
    action();
  }
  return (
    <>
      <PageTitle
        title="系统管理"
        description="管理账号、项目角色和归档记录；所有操作由服务端鉴权并留下审计记录。"
      />
      {[
        users.error,
        projects.error,
        members.error,
        audit.error,
        change.error,
        createUser.error,
        createProject.error,
        archive.error,
        saveMember.error,
      ].map((error, index) => (
        <ErrorNotice key={index} error={error} />
      ))}
      <Panel title="账号管理">
        {users.isPending ? <Loading /> : null}
        <form
          className="toolbar"
          onSubmit={(event) => submit(event, () => createUser.mutate())}
        >
          <label>
            新账号邮箱
            <input
              type="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            初始密码
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={256}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <button disabled={createUser.isPending}>创建账号</button>
        </form>

        <DataTable>
          <thead>
            <tr>
              <th>邮箱</th>
              <th>状态</th>
              <th>系统角色</th>
              <th className="table-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.data?.map((user) => (
              <tr key={user.id}>
                <td>
                  {user.email}
                  <small className="resource-id">{user.id}</small>
                </td>
                <td>{user.active ? "已启用" : "已停用"}</td>
                <td>{user.is_admin ? "系统管理员" : "普通账号"}</td>
                <td className="table-actions">
                  <button
                    className="secondary"
                    disabled={change.isPending || user.id === userId}
                    onClick={() =>
                      change.mutate({
                        id: user.id,
                        values: { active: !user.active },
                      })
                    }
                  >
                    {user.active ? "停用账号" : "启用账号"}
                  </button>
                  <button
                    className="secondary"
                    disabled={change.isPending || user.id === userId}
                    onClick={() =>
                      change.mutate({
                        id: user.id,
                        values: { is_admin: !user.is_admin },
                      })
                    }
                  >
                    {user.is_admin ? "取消系统管理员" : "设为系统管理员"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        {!users.isPending && !users.error && !users.data?.length ? (
          <p className="empty">此页暂无账号。</p>
        ) : null}

        <div className="pagination">
          <button
            className="secondary"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            上一页账号
          </button>
          <span>第 {page + 1} 页</span>
          <button
            className="secondary"
            disabled={(users.data?.length ?? 0) < 50}
            onClick={() => setPage(page + 1)}
          >
            下一页账号
          </button>
        </div>
        <form
          className="toolbar"
          onSubmit={(event) =>
            submit(event, () =>
              change.mutate({
                id: resetUser,
                values: { password: resetPassword },
              }),
            )
          }
        >
          <label>
            重置密码的账号标识
            <input
              required
              value={resetUser}
              onChange={(event) => setResetUser(event.target.value)}
            />
          </label>
          <label>
            新密码
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={256}
              value={resetPassword}
              onChange={(event) => setResetPassword(event.target.value)}
            />
          </label>
          <button disabled={change.isPending}>重置密码并撤销旧会话</button>
        </form>
      </Panel>
      <Panel title="项目与历史记录">
        <p>
          归档会从日常项目列表隐藏整个项目；不删除资源、运行结果和验收证据。原有访问权限保留，可随时恢复。
        </p>
        <form
          className="toolbar"
          onSubmit={(event) => submit(event, () => createProject.mutate())}
        >
          <label>
            新项目名称
            <input
              required
              maxLength={256}
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
            />
          </label>
          <button disabled={createProject.isPending}>创建项目</button>
        </form>

        {projects.isPending ? <Loading /> : null}
        <DataTable>
          <thead>
            <tr>
              <th>项目</th>
              <th>状态</th>
              <th className="table-actions">操作</th>
            </tr>
          </thead>
          <tbody>
            {projects.data?.map((item) => (
              <tr key={item.id}>
                <td>{item.name}</td>
                <td>{item.archived ? "已归档" : "使用中"}</td>
                <td className="table-actions">
                  <button
                    className="secondary"
                    disabled={archive.isPending}
                    aria-label={`${item.archived ? "恢复项目" : "归档项目"} ${item.name}`}
                    onClick={() =>
                      archive.mutate({
                        id: item.id,
                        archived: !item.archived,
                      })
                    }
                  >
                    {item.archived ? "恢复项目" : "归档项目"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        {!projects.isPending && !projects.error && !projects.data?.length ? (
          <p className="empty">暂无项目。</p>
        ) : null}
      </Panel>
      <Panel title="项目成员与角色">
        <label>
          管理项目
          <select
            value={project?.id ?? ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {projects.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
                {item.archived ? "（已归档）" : ""}
              </option>
            ))}
          </select>
        </label>

        {project && members.isPending ? <Loading /> : null}
        <DataTable>
          <thead>
            <tr>
              <th>成员邮箱</th>
              <th>项目角色</th>
              <th>账号状态</th>
            </tr>
          </thead>
          <tbody>
            {members.data?.map((item) => (
              <tr key={item.user_id}>
                <td>{item.email}</td>
                <td>{roleLabels[item.role] ?? item.role}</td>
                <td>{item.active ? "已启用" : "已停用"}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        {project &&
        !members.isPending &&
        !members.error &&
        !members.data?.length ? (
          <p className="empty">此项目暂无成员。</p>
        ) : null}

        <form
          className="toolbar"
          onSubmit={(event) => submit(event, () => saveMember.mutate())}
        >
          <label>
            成员账号标识
            <input
              required
              value={member}
              onChange={(event) => setMember(event.target.value)}
            />
          </label>
          <label>
            项目角色
            <select
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              {Object.entries(roleLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!project || saveMember.isPending}>
            保存成员角色
          </button>
        </form>
      </Panel>
      <Panel title="审计记录">
        {audit.isPending ? <Loading /> : null}
        <DataTable>
          <thead>
            <tr>
              <th>时间</th>
              <th className="table-actions">操作</th>
              <th>操作者</th>
              <th>对象</th>
              <th>变更记录</th>
            </tr>
          </thead>
          <tbody>
            {audit.data?.map((item) => (
              <tr key={item.id}>
                <td>{new Date(item.when).toLocaleString("zh-CN")}</td>
                <td className="table-actions">
                  {auditLabels[item.action] ?? "资源操作"}
                </td>
                <td className="break">{item.who}</td>
                <td className="break">{item.resource}</td>
                <td>
                  <Details title="查看审计详情" value={item} />
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
        {!audit.isPending && !audit.error && !audit.data?.length ? (
          <p className="empty">此页暂无审计记录。</p>
        ) : null}

        <div className="pagination">
          <button
            className="secondary"
            disabled={!auditPage}
            onClick={() => setAuditPage(auditPage - 1)}
          >
            上一页审计
          </button>
          <span>第 {auditPage + 1} 页</span>
          <button
            className="secondary"
            disabled={(audit.data?.length ?? 0) < 50}
            onClick={() => setAuditPage(auditPage + 1)}
          >
            下一页审计
          </button>
        </div>
      </Panel>
    </>
  );
}
