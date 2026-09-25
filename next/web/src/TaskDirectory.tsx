import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { taskSchema } from "./draft";
import { ErrorNotice, purposes } from "./shared";
import { useCatalogSearch } from "./catalogSearch";
const listingSchema = z.object({
  items: z.array(taskSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
});
export function TaskDirectory({
  project,
  purpose,
}: {
  project: string;
  purpose: string;
}) {
  const search = useCatalogSearch(),
    [offset, setOffset] = useState(0),
    [sort, setSort] = useState("updated");
  const query = new URLSearchParams({
    query: search.query,
    offset: String(offset),
    sort,
  });
  if (purpose) query.set("purpose", purpose);
  const listing = useQuery({
    queryKey: ["task-catalog", project, query.toString()],
    queryFn: () =>
      api(`/projects/${project}/task-catalog?${query}`, listingSchema),
  });
  return (
    <section className="task-directory" aria-label="任务目录">
      <div className="section-heading">
        <h2>已有任务</h2>
        <form
          className="directory-search"
          onSubmit={(e) => {
            e.preventDefault();
            search.submit();
            setOffset(0);
          }}
        >
          <label htmlFor="task-directory-search">查找任务</label>
          <input
            id="task-directory-search"
            type="search"
            placeholder="搜索整个项目的任务名称"
            value={search.text}
            onChange={(e) => {
              search.change(e.target.value);
              setOffset(0);
            }}
            onCompositionStart={() => search.compose(true)}
            onCompositionEnd={() => search.compose(false)}
          />
          <label htmlFor="task-directory-sort">排序</label>
          <select
            id="task-directory-sort"
            value={sort}
            onChange={(e) => {
              setSort(e.target.value);
              setOffset(0);
            }}
          >
            <option value="updated">最近修改</option>
            <option value="name">任务名称</option>
          </select>
        </form>
      </div>
      <ErrorNotice error={listing.error} />
      {listing.isPending ? (
        <p role="status">正在读取任务…</p>
      ) : listing.error ? (
        <button type="button" onClick={() => void listing.refetch()}>
          重新读取
        </button>
      ) : !listing.data?.items.length ? (
        <p>
          {search.query || purpose
            ? "没有匹配的任务"
            : "暂无任务，创建后可随时返回继续。"}
        </p>
      ) : (
        <div className="table-scroll">
          <table aria-label="项目任务">
            <thead>
              <tr>
                <th>任务名称</th>
                <th>研究类型</th>
                <th>草稿版本</th>
                <th>最近修改</th>
              </tr>
            </thead>
            <tbody>
              {listing.data.items.map((task) => (
                <tr key={task.id}>
                  <td>
                    <Link to={"/tasks/" + task.id}>{task.draft.title}</Link>
                  </td>
                  <td>{purposes[task.draft.purpose]}</td>
                  <td className="numeric">v{task.revision}</td>
                  <td>{new Date(task.updated * 1000).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pagination" aria-label="任务目录分页">
        <span>
          {listing.data
            ? `共 ${listing.data.total} 项 · 第 ${Math.floor(offset / 20) + 1} 页`
            : "正在读取数量"}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={offset === 0}
          onClick={() => setOffset((v) => Math.max(0, v - 20))}
        >
          上一页
        </button>
        <button
          type="button"
          className="secondary"
          disabled={!listing.data || offset + 20 >= listing.data.total}
          onClick={() => setOffset((v) => v + 20)}
        >
          下一页
        </button>
      </div>
    </section>
  );
}
