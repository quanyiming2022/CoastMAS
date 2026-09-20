import { createContext, useContext, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request, projectSchema } from "./api";
import { ErrorNotice, Loading } from "./components";

interface Workspace {
  projectId: string;
  projectName: string;
}
const WorkspaceContext = createContext<Workspace | null>(null);
export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Workspace is unavailable");
  return value;
}
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: ({ signal }) =>
      request("/projects", z.array(projectSchema), { signal }),
  });
  const [selected, setSelected] = useState("");
  const client = useQueryClient();
  if (projects.isPending) return <Loading />;
  if (projects.error) return <ErrorNotice error={projects.error} />;
  const current =
    projects.data.find((project) => project.id === selected) ??
    projects.data[0];
  if (!current)
    return (
      <section className="panel">
        <h1>尚无可访问的项目</h1>
        <p>请联系项目管理员添加成员权限。</p>
      </section>
    );
  return (
    <WorkspaceContext.Provider
      value={{ projectId: current.id, projectName: current.name }}
    >
      <div className="project-bar">
        <label htmlFor="project-select">当前项目</label>
        <select
          id="project-select"
          value={current.id}
          onChange={(event) => {
            void client.cancelQueries();
            setSelected(event.target.value);
          }}
        >
          {projects.data.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
        <span className="muted">独立版本 · 科学约束 · 可追溯结果</span>
      </div>
      <div key={current.id}>{children}</div>
    </WorkspaceContext.Provider>
  );
}
