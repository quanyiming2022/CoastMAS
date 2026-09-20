import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, revisionSchema } from "./api";
import { useWorkspace } from "./workspace";
import {
  Details,
  display,
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";

export const catalogs = {
  models: ["模型中心", "models"],
  workflows: ["工作流", "workflows"],
  scenes: ["场景空间", "scenes"],
  data: ["数据目录", "data-assets"],
} as const;
export type CatalogKind = keyof typeof catalogs;
export default function Catalog({ kind }: { kind: CatalogKind }) {
  const { projectId } = useWorkspace();
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");
  const [title, endpoint] = catalogs[kind];
  const query = useQuery({
    queryKey: [kind, projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/${endpoint}?project_id=${encodeURIComponent(projectId)}&limit=50&offset=${page * 50}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const items = query.data?.filter((item) =>
    (item.name + " " + item.id).toLowerCase().includes(filter.toLowerCase()),
  );
  return (
    <>
      <PageTitle
        title={title}
        description="项目中的版本化资源；打开详情查看数据来源与科学约束。"
      />
      <div className="toolbar">
        <label>
          筛选本页
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="名称或标识"
          />
        </label>
        <button className="secondary" onClick={() => void query.refetch()}>
          刷新
        </button>
      </div>
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      {items ? (
        <Panel title={`资源 · 第 ${page + 1} 页`}>
          {items.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>类型 / 格式</th>
                    <th>版本</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <Link to={`/${kind}/${encodeURIComponent(item.id)}`}>
                          {item.name}
                        </Link>
                      </td>
                      <td>
                        {display(
                          item.summary.model_type ??
                            item.summary.format ??
                            item.summary.scene_type,
                        )}
                      </td>
                      <td>v{item.version}</td>
                      <td>
                        {!item.enabled ? (
                          <Status value="已停用" />
                        ) : (
                          <Status
                            value={String(
                              item.summary.execution_status ??
                                item.summary.validation_status ??
                                "可查看",
                            )}
                          />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty>{filter ? "当前页没有匹配项。" : "当前页没有资源。"}</Empty>
          )}
          <div className="pagination">
            <button
              disabled={page === 0}
              onClick={() => setPage((value) => value - 1)}
            >
              上一页
            </button>
            <span>每页最多 50 条</span>
            <button
              disabled={(query.data?.length ?? 0) < 50}
              onClick={() => setPage((value) => value + 1)}
            >
              下一页
            </button>
          </div>
        </Panel>
      ) : null}
    </>
  );
}
export function CatalogDetail({ kind }: { kind: CatalogKind }) {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  const [title, endpoint] = catalogs[kind];
  const query = useQuery({
    queryKey: [kind, projectId, id],
    queryFn: ({ signal }) =>
      request(`/${endpoint}/${encodeURIComponent(id)}`, revisionSchema, {
        signal,
      }),
  });
  return (
    <>
      <Link to={"/" + kind}>← 返回{title}</Link>
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      {query.data ? (
        <>
          <PageTitle
            title={display(
              query.data.spec.display_name ?? query.data.spec.name,
            )}
            description={
              "版本 " + query.data.version + " · " + query.data.resource_id
            }
          />
          <Panel title="资源说明">
            <p>
              {display(
                query.data.spec.description ??
                  query.data.spec.management_goal ??
                  query.data.spec.source,
              )}
            </p>
            {query.data.spec.validation_status ? (
              <Status value={String(query.data.spec.validation_status)} />
            ) : null}
            {query.data.spec.execution_status ? (
              <Status value={String(query.data.spec.execution_status)} />
            ) : null}
            <dl>
              <dt>校验摘要</dt>
              <dd className="break">{query.data.checksum}</dd>
            </dl>
          </Panel>
          {[
            "inputs",
            "outputs",
            "parameters",
            "constraints",
            "variables",
            "quality",
            "required_outputs",
            "time_range",
            "study_area",
          ]
            .filter((key) => query.data.spec[key] !== undefined)
            .map((key) => (
              <Panel key={key} title={fieldNames[key] ?? key}>
                <StructuredValue value={query.data.spec[key]} />
              </Panel>
            ))}
          <Details title="完整版本契约" value={query.data.spec} />
        </>
      ) : null}
    </>
  );
}
const fieldNames: Record<string, string> = {
  inputs: "输入变量",
  outputs: "输出变量",
  parameters: "参数",
  constraints: "科学约束",
  variables: "变量",
  quality: "质量记录",
  required_outputs: "必要输出",
  time_range: "时间范围",
  study_area: "研究范围",
};
function StructuredValue({ value }: { value: unknown }) {
  if (Array.isArray(value))
    return (
      <ul className="value-list">
        {value.map((item: unknown, index) => (
          <li key={index}>
            <StructuredValue value={item} />
          </li>
        ))}
      </ul>
    );
  const parsed = z.record(z.string(), z.unknown()).safeParse(value);
  if (parsed.success)
    return (
      <dl className="definition-grid">
        {Object.entries(parsed.data).map(([key, item]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{display(item)}</dd>
          </div>
        ))}
      </dl>
    );
  return <span>{display(value)}</span>;
}
