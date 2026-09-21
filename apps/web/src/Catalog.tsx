import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import {
  request,
  resourceSchema,
  revisionSchema,
  type ResourceSummary,
} from "./api";
import { modelContract } from "./contracts";
import schema from "../contracts.schema.json";
import { modelTypes } from "./model-editor";
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
  return (
    <CatalogList
      key={`${projectId}:${kind}`}
      kind={kind}
      projectId={projectId}
    />
  );
}
function CatalogList({
  kind,
  projectId,
}: {
  kind: CatalogKind;
  projectId: string;
}) {
  const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("");
  const [capability, setCapability] = useState("");
  const [modelType, setModelType] = useState("");
  const [enabled, setEnabled] = useState("");
  const [dataType, setDataType] = useState("");
  const [dataFormat, setDataFormat] = useState("");
  const [dataCrs, setDataCrs] = useState("");
  const [search, setSearch] = useState({
    q: "",
    capability: "",
    model_type: "",
    enabled: "",
    data_type: "",
    data_format: "",
    crs: "",
  });
  const [title, endpoint] = catalogs[kind];
  const query = useQuery({
    queryKey: [kind, projectId, page, search],
    queryFn: async ({
      signal,
    }): Promise<
      Pick<ResourceSummary, "id" | "name" | "version" | "enabled" | "summary">[]
    > => {
      const parameters = new URLSearchParams({
        project_id: projectId,
        limit: "50",
        offset: String(page * 50),
      });
      if (kind === "models") {
        for (const [key, value] of Object.entries(search))
          if (value) parameters.set(key, value);
        const found = await request(
          `/models/search?${parameters}`,
          z.array(
            z.object({
              id: z.string(),
              name: z.string(),
              version: z.number(),
              enabled: z.boolean(),
              spec: modelContract,
            }),
          ),
          { signal },
        );
        return found.map(({ spec, ...item }) => ({
          ...item,
          summary: {
            model_type: spec.model_type,
            validation_status: spec.validation_status,
            execution_status: spec.execution_status,
          },
        }));
      }
      if (kind === "data") {
        for (const [key, value] of Object.entries(search))
          if (value) parameters.set(key, value);
      }
      return request(
        `/${endpoint}${kind === "data" ? "/search" : ""}?${parameters}`,
        z.array(resourceSchema),
        {
          signal,
        },
      );
    },
  });
  const items =
    kind === "models" || kind === "data"
      ? query.data
      : query.data?.filter((item) =>
          (item.name + " " + item.id)
            .toLowerCase()
            .includes(filter.toLowerCase()),
        );
  return (
    <>
      <PageTitle
        title={title}
        description="项目中的版本化资源；打开详情查看数据来源与科学约束。"
      />
      <div className="toolbar">
        {kind === "data" ? (
          <>
            <Link to="/data/new">上传数据</Link>
            <Link to="/data-sources">外部数据源</Link>
          </>
        ) : null}
        {kind === "models" ? (
          <Link to="/models/new">新增或导入模型</Link>
        ) : null}
        {kind === "scenes" ? <Link to="/scenes/new">新建场景</Link> : null}
        {kind === "workflows" ? (
          <Link to="/workflows/new">新建工作流</Link>
        ) : null}
        <label>
          {kind === "models"
            ? "搜索全部模型"
            : kind === "data"
              ? "搜索全部数据"
              : "筛选本页"}
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="名称或标识"
          />
        </label>
        {kind === "models" ? (
          <>
            <Link to="/models/decompose">静态拆解模型</Link>
            <label>
              所需能力
              <input
                value={capability}
                onChange={(event) => setCapability(event.target.value)}
              />
            </label>
            <label>
              筛选模型类型
              <select
                value={modelType}
                onChange={(event) => setModelType(event.target.value)}
              >
                <option value="">全部类型</option>
                {modelTypes.map((type) => (
                  <option key={type}>{type}</option>
                ))}
              </select>
            </label>
            <label>
              模型启用状态
              <select
                value={enabled}
                onChange={(event) => setEnabled(event.target.value)}
              >
                <option value="">全部状态</option>
                <option value="true">已启用</option>
                <option value="false">已停用</option>
              </select>
            </label>
            <button
              onClick={() => {
                setSearch({
                  q: filter.trim(),
                  capability: capability.trim(),
                  model_type: modelType,
                  enabled,
                  data_type: "",
                  data_format: "",
                  crs: "",
                });
                setPage(0);
              }}
            >
              搜索模型
            </button>
          </>
        ) : null}
        {kind === "data" ? (
          <>
            <label>
              数据类别筛选
              <select
                value={dataType}
                onChange={(event) => setDataType(event.target.value)}
              >
                <option value="">全部类别</option>
                {schema.$defs.DataAssetSpec.properties.type.enum.map(
                  (value) => (
                    <option key={value}>{value}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              文件格式筛选
              <select
                value={dataFormat}
                onChange={(event) => setDataFormat(event.target.value)}
              >
                <option value="">全部格式</option>
                {schema.$defs.DataAssetSpec.properties.format.enum.map(
                  (value) => (
                    <option key={value}>{value}</option>
                  ),
                )}
              </select>
            </label>
            <label>
              坐标参考系筛选
              <input
                value={dataCrs}
                onChange={(event) => setDataCrs(event.target.value)}
                placeholder="例如 EPSG:32650"
              />
            </label>
            <button
              onClick={() => {
                setPage(0);
                setSearch({
                  q: filter.trim(),
                  data_type: dataType,
                  data_format: dataFormat,
                  crs: dataCrs.trim(),
                  capability: "",
                  model_type: "",
                  enabled: "",
                });
              }}
            >
              搜索数据
            </button>
          </>
        ) : null}
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
                        <small className="resource-id" title={item.id}>
                          …{item.id.slice(-12)}
                        </small>
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
      {kind === "scenes" ? (
        <Link to={`/scenes/${encodeURIComponent(id)}/workspace`}>
          打开场景工作台
        </Link>
      ) : null}
      {kind === "models" ? (
        <Link to={`/models/${encodeURIComponent(id)}/edit`}>管理模型版本</Link>
      ) : null}
      {kind === "data" ? (
        <Link to={`/data/${encodeURIComponent(id)}/workspace`}>
          管理数据版本与预览
        </Link>
      ) : null}
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
