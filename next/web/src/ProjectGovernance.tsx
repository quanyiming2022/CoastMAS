import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { ErrorNotice } from "./shared";
import { useCatalogSearch } from "./catalogSearch";

export function ProjectSources({ project }: { project: string }) {
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const listing = useQuery({
    queryKey: ["local-sources", project],
    queryFn: () =>
      api(
        `/projects/${project}/local-sources`,
        z.array(
          z.object({ id: z.string(), name: z.string(), granted: z.boolean() }),
        ),
      ),
  });
  const user = useQuery({
    queryKey: ["governance-session"],
    queryFn: () => api("/session", z.object({ system_admin: z.boolean() })),
  });
  return (
    <section aria-label="项目数据源授权">
      <h3>数据源授权</h3>
      <p>授权允许从来源导入；资料库只列出已完成的受管资料。</p>
      <ErrorNotice error={error ?? listing.error} />
      {listing.data?.map((source) => (
        <div className="actions" key={source.id}>
          <span>
            {source.name} · {source.granted ? "已授权" : "未授权"}
          </span>
          {user.data?.system_admin ? (
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                setError(null);
                try {
                  await api(
                    `/projects/${project}/local-sources/${source.id}/grant`,
                    z.unknown(),
                    { method: source.granted ? "DELETE" : "POST" },
                  );
                  await listing.refetch();
                } catch (e) {
                  setError(e);
                } finally {
                  setBusy(false);
                }
              }}
            >
              {source.granted ? "撤销授权" : "授权来源"}
            </button>
          ) : null}
        </div>
      ))}
      {listing.data?.length === 0 ? (
        <p>暂无对当前角色可用的来源连接。</p>
      ) : null}
    </section>
  );
}
export function AuditLog({ project }: { project?: string }) {
  const search = useCatalogSearch(),
    [offset, setOffset] = useState(0);
  const events = useQuery({
    queryKey: ["audit-query", project, search.query, offset],
    queryFn: () =>
      api(
        "/management/audit?" +
          new URLSearchParams({
            project: project ?? "",
            search: search.query,
            offset: String(offset),
          }),
        z.object({
          items: z.array(
            z.object({
              id: z.string(),
              email: z.string().nullable(),
              action_label: z.string(),
              target: z.string(),
              target_name: z.string().nullable(),
              created: z.number(),
            }),
          ),
          total: z.number(),
        }),
      ),
  });
  return (
    <section aria-label={project ? "项目活动" : "审计日志"}>
      <div className="catalog-toolbar">
        <h2>{project ? "项目活动" : "审计日志"}</h2>
        <label>
          搜索审计
          <input
            type="search"
            value={search.text}
            onChange={(event) => {
              search.change(event.target.value);
              setOffset(0);
            }}
            onCompositionStart={() => search.compose(true)}
            onCompositionEnd={() => search.compose(false)}
            onKeyDown={(event) => {
              if (event.key === "Enter") search.submit();
            }}
          />
        </label>
      </div>
      <ErrorNotice error={events.error} />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>操作者</th>
              <th>动作</th>
              <th>对象</th>
            </tr>
          </thead>
          <tbody>
            {events.data?.items.map((event) => (
              <tr key={event.id}>
                <td>{new Date(event.created * 1000).toLocaleString()}</td>
                <td>{event.email ?? "历史账号"}</td>
                <td>{event.action_label}</td>
                <td>
                  {event.target_name ?? "历史对象"}{" "}
                  <details>
                    <summary>标识</summary>
                    <code>{event.target}</code>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        navigator.clipboard.writeText(event.target)
                      }
                    >
                      复制
                    </button>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {events.isPending ? (
        <p role="status">正在读取审计…</p>
      ) : events.data?.items.length === 0 ? (
        <p>没有匹配记录</p>
      ) : null}
      <div className="pagination">
        <span>共{events.data?.total ?? 0}条</span>
        <button
          type="button"
          className="secondary"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 25))}
        >
          上一页
        </button>
        <button
          type="button"
          className="secondary"
          disabled={offset + 25 >= (events.data?.total ?? 0)}
          onClick={() => setOffset(offset + 25)}
        >
          下一页
        </button>
      </div>
    </section>
  );
}
