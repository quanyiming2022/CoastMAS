import { useState } from "react";
import {
  createBrowserRouter,
  RouterProvider,
  Route,
  Routes,
  useNavigate,
  useParams,
  useLocation,
  useMatch,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { z } from "zod";
import { api, actorSchema, setCSRF, projectSchema } from "./api";
import { taskSchema } from "./draft";
import { ErrorNotice } from "./shared";
import { AuditLog } from "./ProjectGovernance";
import { Administration } from "./Administration";
import { MethodEditor } from "./Methods";
import { SpatialWorkspace } from "./SpatialWorkspace";
import { WorkbenchShell } from "./WorkbenchShell";
import { ComparisonTask } from "./ComparisonTask";
import { TaskWorkspace } from "./TaskWorkspace";
import { ResearchWorkspace } from "./ResearchWorkspace";
import { ManagementCenter } from "./ManagementCenter";
import "./style.css";
import "./workbench.css";
import "./desktop-theme.css";
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
function Login() {
  const client = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <h1>CoastMAS</h1>
      <p>海岸带科研任务工作台</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            const response = await api(
              "/session",
              z.object({ csrf: z.string(), user: actorSchema }),
              { method: "POST", body: JSON.stringify({ email, password }) },
            );
            // Keep the mounted session observer; remove only prior actor data.
            client.removeQueries({
              predicate: (query) => query.queryKey[0] !== "session",
            });
            setCSRF(response.csrf);
            client.setQueryData(["session"], response.user);
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          邮箱
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          密码
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <ErrorNotice error={error} />
        <button disabled={busy}>登录</button>
      </form>
    </main>
  );
}
function TaskRoute({ canEdit }: { canEdit: boolean }) {
  const { id = "" } = useParams();
  const task = useQuery({
    queryKey: ["task", id],
    queryFn: () => api(`/tasks/${id}`, taskSchema),
  });
  return task.isPending ? (
    <p role="status">正在恢复服务器草稿…</p>
  ) : task.data ? (
    task.data.draft.options.editor === "method" ? (
      <MethodEditor key={id} initial={task.data} canEdit={canEdit} />
    ) : task.data.draft.purpose === "spatial" ? (
      <SpatialWorkspace key={id} task={task.data} canEdit={canEdit} />
    ) : task.data.draft.purpose === "comparison" ? (
      <ComparisonTask key={id} initial={task.data} canEdit={canEdit} />
    ) : (
      <TaskWorkspace key={id} initial={task.data} canEdit={canEdit} />
    )
  ) : (
    <ErrorNotice error={task.error} />
  );
}
function Shell() {
  const [headerHost, setHeaderHost] = useState<HTMLDivElement | null>(null);
  const client = useQueryClient();
  const session = useQuery({
    queryKey: ["session"],
    queryFn: async () => {
      const user = await api("/session", actorSchema);
      setCSRF(user.csrf);
      return user;
    },
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api("/projects", z.array(projectSchema)),
    enabled: !!session.data,
  });
  const location = useLocation(),
    navigate = useNavigate(),
    match = useMatch("/tasks/:id");
  const currentTask = useQuery({
    queryKey: ["task", match?.params.id],
    enabled: !!session.data && !!match,
    queryFn: () => api(`/tasks/${match!.params.id}`, taskSchema),
  });
  const requestedProject = new URLSearchParams(location.search).get("project");
  const project = match
    ? (currentTask.data?.project_id ?? "")
    : requestedProject
      ? (projects.data?.find((p) => p.id === requestedProject)?.id ?? "")
      : (projects.data?.[0]?.id ?? "");
  const projectRole = projects.data?.find((p) => p.id === project)?.role;

  if (session.isPending) return <p role="status">正在连接科研工作台…</p>;
  if (!session.data) return <Login />;
  return (
    <WorkbenchShell
      onHeaderHost={setHeaderHost}
      taskPurpose={
        currentTask.data?.draft.options.editor === "method"
          ? "method"
          : currentTask.data?.draft.purpose
      }
      project={project}
      email={session.data.email}
      canManage={session.data.system_admin || projectRole === "manager"}
      systemAdmin={session.data.system_admin}
      onSignOut={async () => {
        await api("/session", z.object({ signed_out: z.boolean() }), {
          method: "DELETE",
        });
        setCSRF("");
        client.removeQueries({
          predicate: (query) => query.queryKey[0] !== "session",
        });
        client.setQueryData(["session"], null);
      }}
      projectControl={
        <label>
          <span className="visually-hidden">当前项目</span>
          <select
            title={projects.data?.find((p) => p.id === project)?.name}
            value={project}
            disabled={!!match && currentTask.isPending}
            onChange={(e) =>
              navigate(
                "/research?project=" + encodeURIComponent(e.target.value),
              )
            }
          >
            {!project ? (
              <option value="" disabled>
                请选择可访问项目
              </option>
            ) : null}
            {projects.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      }
    >
      <ErrorNotice error={projects.error} />
      {project ||
      (session.data.system_admin &&
        (location.pathname.startsWith("/management/") || location.pathname === "/projects")) ? (
        <>
          {project ? (
            <ResearchWorkspace
              headerHost={headerHost}
              key={project}
              project={project}
              canEdit={!!projectRole && projectRole !== "viewer"}
              routeTaskId={
                currentTask.data?.draft.options.editor === "method"
                  ? undefined
                  : match?.params.id
              }
              hidden={
                (location.pathname.startsWith("/management/") || location.pathname === "/projects") ||
                currentTask.data?.draft.options.editor === "method"
              }
            />
          ) : null}
          <Routes>
            <Route path="/management/audit" element={<AuditLog project={session.data.system_admin ? undefined : project} />} />
            <Route
              path="/management/users"
              element={
                <ManagementCenter
                  key="users"
                  kind="users"
                  project={project}
                  onEnter={(id) => navigate("/research?project=" + id)}
                />
              }
            />
            <Route
              path="/projects"
              element={
                <ManagementCenter
                  key="projects"
                  kind="projects"
                  project={project}
                  onEnter={(id) => navigate("/research?project=" + id)}
                />
              }
            />
            <Route
              path="/management/settings"
              element={<Administration project={project} user={session.data} />}
            />
          </Routes>
          {currentTask.data?.draft.options.editor === "method" ? (
            <TaskRoute canEdit={!!projectRole && projectRole !== "viewer"} />
          ) : null}
        </>
      ) : match && currentTask.isPending ? (
        <p role="status">正在恢复任务所属项目…</p>
      ) : (
        <>
          <ErrorNotice error={currentTask.error} />
          <p>当前账号没有可访问项目，请联系项目管理员。</p>
        </>
      )}
    </WorkbenchShell>
  );
}
const router = createBrowserRouter([{ path: "*", element: <Shell /> }]);
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
