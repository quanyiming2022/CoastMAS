import { lazy, Suspense, useEffect, useState, type FormEvent } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { z } from "zod";
import { ApiError, request, userSchema, SESSION_EXPIRED } from "./api";
import { ErrorNotice, Loading } from "./components";
import { WorkspaceProvider } from "./workspace";
import type { CatalogKind } from "./Catalog";
const CatalogDetail = lazy(() =>
  import("./Catalog").then((module) => ({ default: module.CatalogDetail })),
);
const Admin = lazy(() => import("./Admin"));
const KnowledgeGraph = lazy(() => import("./KnowledgeGraph"));
const Entities = lazy(() => import("./Entities"));
const Planner = lazy(() => import("./Planner"));
const Runs = lazy(() => import("./Runs"));
const RunDetail = lazy(() =>
  import("./Runs").then((module) => ({ default: module.RunDetail })),
);
const ResultComparison = lazy(() => import("./ResultComparison"));
const Results = lazy(() => import("./Results"));
const ResultDetail = lazy(() =>
  import("./Results").then((module) => ({ default: module.ResultDetail })),
);
const ModelDecomposer = lazy(() => import("./ModelDecomposer"));
const SpatialOptimization = lazy(() => import("./SpatialOptimization"));
const SpatialOptimizationEditor = lazy(() =>
  import("./SpatialOptimization").then((module) => ({
    default: module.OptimizationEditor,
  })),
);
const SpatialOptimizationRecord = lazy(() =>
  import("./SpatialOptimization").then((module) => ({
    default: module.OptimizationRecord,
  })),
);
const Collaboration = lazy(() => import("./Collaboration"));
const AssessmentRecords = lazy(() => import("./AssessmentRecords"));
const AssessmentRecord = lazy(() =>
  import("./AssessmentRecords").then((module) => ({
    default: module.AssessmentRecord,
  })),
);
const IndicatorFrameworks = lazy(() => import("./IndicatorFrameworks"));
const IndicatorFrameworkEditor = lazy(() =>
  import("./IndicatorFrameworks").then((module) => ({
    default: module.IndicatorFrameworkEditor,
  })),
);
const DataSources = lazy(() => import("./DataSources"));
const SourceEditor = lazy(() =>
  import("./DataSources").then((module) => ({ default: module.SourceEditor })),
);
const DataWorkspace = lazy(() => import("./DataWorkspace"));
const ModelEditor = lazy(() => import("./ModelEditor"));
const SceneWorkspace = lazy(() => import("./SceneWorkspace"));
const WorkflowEditor = lazy(() => import("./WorkflowEditor"));
const Workflow = lazy(() => import("./Workflow"));
const Dashboard = lazy(() => import("./Dashboard"));
const Catalog = lazy(() => import("./Catalog"));
const navigation = [
  ["/dashboard", "项目概览"],
  ["/models", "模型中心"],
  ["/knowledge-graph", "知识图谱"],
  ["/planner", "智能规划"],
  ["/workflows", "工作流"],
  ["/scenes", "场景空间"],
  ["/entities", "地理实体"],
  ["/data", "数据目录"],
  ["/runs", "运行中心"],
  ["/results", "结果中心"],
  ["/assessments", "评价中心"],
  ["/collaboration", "协同方案"],
  ["/optimizations", "空间优化"],
] as const;

async function clearProtectedData(client: QueryClient): Promise<void> {
  await client.cancelQueries({
    predicate: (query) => query.queryKey[0] !== "current-user",
  });
  client.removeQueries({
    predicate: (query) => query.queryKey[0] !== "current-user",
  });
}

export default function App() {
  const location = useLocation();
  const client = useQueryClient();
  const user = useQuery({
    queryKey: ["current-user"],
    queryFn: ({ signal }) => request("/auth/me", userSchema, { signal }),
    retry: false,
  });
  useEffect(() => {
    let expiring = false;
    const expire = () => {
      if (expiring) return;
      expiring = true;
      void clearProtectedData(client)
        .then(() => client.invalidateQueries({ queryKey: ["current-user"] }))
        .finally(() => {
          expiring = false;
        });
    };
    window.addEventListener(SESSION_EXPIRED, expire);
    return () => window.removeEventListener(SESSION_EXPIRED, expire);
  }, [client]);
  const logout = useMutation({
    mutationFn: () => request("/auth/logout", z.null(), { method: "POST" }),
    onSuccess: async () => {
      await clearProtectedData(client);
      await client.resetQueries({ queryKey: ["current-user"] });
    },
  });
  if (user.isPending)
    return (
      <main className="center">
        <Loading />
      </main>
    );
  if (user.error instanceof ApiError && user.error.status === 401)
    return <Login />;
  if (user.error)
    return (
      <main className="center">
        <ErrorNotice error={user.error} />
        <button onClick={() => void user.refetch()}>重试</button>
      </main>
    );
  if (!user.data) return null;
  if (location.pathname === "/login")
    return <Navigate replace to="/dashboard" />;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/dashboard">
          <span className="brand-mark">≈</span>
          <span>
            CoastMAS<small>海岸带科学协同平台</small>
          </span>
        </NavLink>
        <p className="nav-label">项目工作空间</p>
        <nav aria-label="主导航">
          {navigation.map(([path, title]) => (
            <NavLink key={path} to={path}>
              {title}
            </NavLink>
          ))}
          {user.data.is_admin ? <NavLink to="/admin">系统管理</NavLink> : null}
        </nav>
        <div className="sidebar-foot">
          <small>{user.data.email}</small>
          <button
            className="secondary"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            退出登录
          </button>
        </div>
      </aside>
      <main className="main-content">
        <ErrorNotice error={logout.error} />
        {location.pathname === "/admin" && user.data.is_admin ? (
          <Suspense fallback={<Loading />}>
            <Admin userId={user.data.user_id} />
          </Suspense>
        ) : (
          <WorkspaceProvider>
            <Suspense fallback={<Loading />}>
              <Routes>
                <Route
                  path="/"
                  element={<Navigate replace to="/dashboard" />}
                />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/knowledge-graph" element={<KnowledgeGraph />} />
                <Route path="/entities" element={<Entities />} />
                <Route
                  path="/optimizations"
                  element={<SpatialOptimization />}
                />
                <Route
                  path="/optimizations/new"
                  element={<SpatialOptimizationEditor />}
                />
                <Route
                  path="/optimizations/:id"
                  element={<SpatialOptimizationRecord />}
                />
                <Route path="/collaboration" element={<Collaboration />} />
                <Route path="/planner" element={<Planner />} />
                <Route path="/models/decompose" element={<ModelDecomposer />} />
                <Route
                  path="/assessment-records"
                  element={<AssessmentRecords />}
                />
                <Route
                  path="/assessment-records/:id"
                  element={<AssessmentRecord />}
                />
                <Route path="/assessments" element={<IndicatorFrameworks />} />
                <Route
                  path="/assessments/new"
                  element={<IndicatorFrameworkEditor />}
                />
                <Route
                  path="/assessments/:id"
                  element={<IndicatorFrameworkEditor />}
                />
                <Route path="/data-sources" element={<DataSources />} />
                <Route path="/data-sources/new" element={<SourceEditor />} />
                <Route path="/data-sources/:id" element={<SourceEditor />} />
                <Route path="/data/new" element={<DataWorkspace />} />
                <Route path="/data/:id/workspace" element={<DataWorkspace />} />
                <Route path="/models/new" element={<ModelEditor />} />
                <Route path="/models/:id/edit" element={<ModelEditor />} />
                <Route path="/scenes/new" element={<SceneWorkspace />} />
                <Route
                  path="/scenes/:id/workspace"
                  element={<SceneWorkspace />}
                />
                <Route path="/workflows/new" element={<WorkflowEditor />} />
                <Route
                  path="/workflows/:id/edit"
                  element={<WorkflowEditor />}
                />
                <Route path="/runs" element={<Runs />} />
                <Route path="/runs/:id" element={<RunDetail />} />
                <Route path="/results" element={<Results />} />
                <Route path="/results/compare" element={<ResultComparison />} />
                <Route path="/results/:id" element={<ResultDetail />} />
                {(
                  [
                    "models",
                    "workflows",
                    "scenes",
                    "data",
                  ] satisfies CatalogKind[]
                ).flatMap((kind) => [
                  <Route
                    key={kind}
                    path={"/" + kind}
                    element={<Catalog kind={kind} />}
                  />,
                  <Route
                    key={kind + "-detail"}
                    path={`/${kind}/:id`}
                    element={
                      kind === "workflows" ? (
                        <Workflow />
                      ) : (
                        <CatalogDetail kind={kind} />
                      )
                    }
                  />,
                ])}
                <Route
                  path="*"
                  element={
                    <section className="panel">
                      <h1>页面不存在</h1>
                      <NavLink to="/dashboard">返回项目概览</NavLink>
                    </section>
                  }
                />
              </Routes>
            </Suspense>
          </WorkspaceProvider>
        )}
      </main>
    </div>
  );
}
function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const client = useQueryClient();
  const login = useMutation({
    mutationFn: () =>
      request(
        "/auth/login",
        z.object({ user_id: z.string(), csrf_token: z.string() }),
        { method: "POST", body: { email, password } },
      ),
    onSuccess: async () => {
      setPassword("");
      await clearProtectedData(client);
      await client.invalidateQueries({ queryKey: ["current-user"] });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate();
  }
  return (
    <main className="login-page">
      <section className="login-story">
        <span className="eyebrow">
          COASTAL SCIENCE · REPRODUCIBLE DECISIONS
        </span>
        <h1>
          连接模型、数据
          <br />
          与海岸带决策。
        </h1>
        <p>让每一次分析有清晰的约束、可验证的计算和完整的来源。</p>
        <div className="coast-lines" aria-hidden="true">
          ≈
        </div>
      </section>
      <section className="login-card">
        <span className="brand-text">CoastMAS</span>
        <h2>登录工作空间</h2>
        <p className="muted">使用管理员分配的账号继续。</p>
        <form onSubmit={submit}>
          <label>
            邮箱
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            密码
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <ErrorNotice error={login.error} />
          <button type="submit" disabled={login.isPending}>
            {login.isPending ? "正在登录…" : "登录"}
          </button>
        </form>
        <small className="muted">权限与科学约束由服务端执行。</small>
      </section>
    </main>
  );
}
