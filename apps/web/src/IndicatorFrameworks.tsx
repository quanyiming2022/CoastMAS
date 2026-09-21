import { DataTable } from "./components";
import FrameworkPlanning from "./FrameworkPlanning";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, revisionSchema } from "./api";
import { contract } from "./contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle, Panel } from "./components";
import {
  frameworkContract,
  frameworkDraft,
  type FrameworkDraft,
  freshFramework,
  freshIndicator,
  prepareFrameworkRevision,
  setWeightMethod,
} from "./indicator-editor";
import type {
  IndicatorDefinition,
  IndicatorFrameworkSpec,
} from "./generated/contracts";
const revisionContract = revisionSchema.extend({ spec: frameworkContract });
const categoriesContract = z.object({
  label: z.literal("DEMO FRAMEWORK"),
  categories: z.array(z.string()),
});

export default function IndicatorFrameworks() {
  const { projectId } = useWorkspace();
  return <FrameworkList key={projectId} projectId={projectId} />;
}
function FrameworkList({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: ["frameworks", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/indicator-frameworks?${new URLSearchParams({ project_id: projectId, limit: "50", offset: String(page * 50) })}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  return (
    <>
      <PageTitle
        title="综合评价"
        description="管理指标体系，准备固定版本的评价输入，并通过科学工作流计算状态与多期变化。"
      />
      <div className="toolbar">
        <Link to="/assessments/new">新建指标体系</Link>
        <Link to="/assessment-records">查看评价记录</Link>
        <Link to="/results">查看评价结果</Link>
      </div>
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        <Panel title="指标体系">
          <DataTable>
            <thead>
              <tr>
                <th>名称</th>
                <th className="numeric">当前版本</th>
                <th className="table-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {query.data?.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td className="numeric">v{row.version}</td>
                  <td className="table-actions">
                    <Link to={`/assessments/${encodeURIComponent(row.id)}`}>
                      编辑与准备数据
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          {!query.error && !query.data?.length ? <p>尚无指标体系。</p> : null}
        </Panel>
      )}
      <div className="pagination">
        <button
          className="secondary"
          disabled={!page || query.isFetching}
          onClick={() => setPage(page - 1)}
        >
          上一页
        </button>
        <span>第 {page + 1} 页</span>
        <button
          className="secondary"
          disabled={query.data?.length !== 50 || query.isFetching}
          onClick={() => setPage(page + 1)}
        >
          下一页
        </button>
      </div>
    </>
  );
}
export function IndicatorFrameworkEditor() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  return (
    <Editor key={`${projectId}:${id ?? "new"}`} id={id} projectId={projectId} />
  );
}
function Editor({ id, projectId }: { id?: string; projectId: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [parameters] = useSearchParams();
  const [fresh] = useState(freshFramework);
  const [version, setVersion] = useState(() => {
    const value = Number(parameters.get("version"));
    return Number.isInteger(value) && value > 0 ? value : 0;
  });
  const [draft, setDraft] = useState<FrameworkDraft | null>(null);
  const [dataId, setDataId] = useState("");
  const [dataVersion, setDataVersion] = useState(1);
  const [search, setSearch] = useState("");
  const [lookup, setLookup] = useState("");
  const [key, setKey] = useState(() => crypto.randomUUID());
  const query = useQuery({
    queryKey: ["framework-editor", projectId, id, version],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/indicator-frameworks/${encodeURIComponent(id!)}${version ? `?version=${version}` : ""}`,
        revisionContract,
        { signal },
      ),
  });
  const history = useQuery({
    queryKey: ["framework-history", projectId, id],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/indicator-frameworks/${encodeURIComponent(id!)}/versions`,
        z.array(revisionContract),
        { signal },
      ),
  });
  const categories = useQuery({
    queryKey: ["framework-categories", projectId],
    queryFn: ({ signal }) =>
      request("/indicator-frameworks/demo-categories", categoriesContract, {
        signal,
      }),
  });
  const assets = useQuery({
    queryKey: ["framework-assets", projectId, lookup],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/data-assets/search?${new URLSearchParams({ project_id: projectId, q: lookup, data_type: "json", data_format: "JSON", limit: "50" })}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const base = query.data?.spec ?? null;
  const current = draft ?? (base ? frameworkDraft(base) : fresh);
  const historical = version !== 0;
  const prepared = useMutation({
    mutationFn: () =>
      request(
        `/indicator-frameworks/${encodeURIComponent(id!)}/prepare`,
        revisionSchema.extend({ spec: contract("DataAssetSpec") }),
        {
          method: "POST",
          body: {
            expected_version: base!.version,
            data: { id: dataId, version: dataVersion },
            idempotency_key: key,
          },
        },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["data"] }),
  });
  const save = useMutation({
    mutationFn: () => {
      const spec = prepareFrameworkRevision(current, base);
      return request(
        id
          ? `/indicator-frameworks/${encodeURIComponent(id)}`
          : "/indicator-frameworks",
        revisionContract,
        {
          method: id ? "PUT" : "POST",
          body: id
            ? { expected_version: base!.version, spec }
            : { project_id: projectId, spec },
        },
      );
    },
    onSuccess: async (row) => {
      client.setQueryData(
        ["framework-editor", projectId, row.resource_id, 0],
        row,
      );
      setDraft(null);
      setVersion(0);
      prepared.reset();
      setKey(crypto.randomUUID());
      navigate(`/assessments/${encodeURIComponent(row.resource_id)}`, {
        replace: true,
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["frameworks"] }),
        client.invalidateQueries({ queryKey: ["framework-history"] }),
      ]);
    },
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/indicator-frameworks/${encodeURIComponent(id!)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["frameworks"] });
      navigate("/assessments");
    },
  });
  const busy = save.isPending || prepared.isPending || archive.isPending;
  function change(next: FrameworkDraft) {
    setDraft(next);
    prepared.reset();
  }
  function editIndicator(index: number, next: IndicatorDefinition) {
    change({
      ...current,
      indicators: current.indicators.map((item, i) =>
        i === index ? next : item,
      ),
    });
  }
  function selectInput(identifier: string, revision: number) {
    setDataId(identifier);
    setDataVersion(revision);
    setKey(crypto.randomUUID());
    prepared.reset();
  }
  if (id && query.isPending) return <Loading />;
  if (id && (!base || query.error))
    return <ErrorNotice error={query.error ?? new Error("指标体系不可用")} />;
  return (
    <>
      <Link to="/assessments">← 返回综合评价</Link>
      <PageTitle
        title={id ? "指标体系版本管理" : "新建指标体系"}
        description="指标边界、公式、方向与权重必须明确；固定参考范围用于保持多期可比性。"
      />
      <ErrorNotice
        error={
          query.error ??
          history.error ??
          categories.error ??
          assets.error ??
          save.error ??
          prepared.error ??
          archive.error
        }
      />
      {id ? (
        <Panel title="历史版本">
          <label>
            查看指标体系版本
            <select
              value={version}
              disabled={busy}
              onChange={(event) => {
                setVersion(Number(event.target.value));
                setDraft(null);
                prepared.reset();
                setKey(crypto.randomUUID());
              }}
            >
              <option value={0}>当前版本</option>
              {history.data?.map((row) => (
                <option key={row.version} value={row.version}>
                  v{row.version} · {row.spec.name}
                </option>
              ))}
            </select>
          </label>
          {historical ? (
            <p>历史版本只读，后续修订不会改变既有评价输入。</p>
          ) : null}
        </Panel>
      ) : null}
      <fieldset
        className="scene-form form-workspace"
        disabled={historical || busy}
      >
        <Panel title="体系说明">
          <div className="form-grid">
            <label>
              体系名称
              <input
                value={current.name}
                onChange={(event) =>
                  change({ ...current, name: event.target.value })
                }
              />
            </label>
            <label>
              依据与适用范围
              <textarea
                value={current.description}
                onChange={(event) =>
                  change({ ...current, description: event.target.value })
                }
              />
            </label>
            <label>
              空间评价单元
              <select
                value={current.spatial_support}
                onChange={(event) =>
                  change({
                    ...current,
                    spatial_support: event.target
                      .value as IndicatorFrameworkSpec["spatial_support"],
                  })
                }
              >
                <option value="management_unit">管理单元</option>
                <option value="administrative_unit">行政单元</option>
                <option value="custom_polygon">自定义多边形</option>
                <option value="grid">网格</option>
              </select>
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={current.demo}
                onChange={(event) =>
                  change({ ...current, demo: event.target.checked })
                }
              />
              示范体系（DEMO FRAMEWORK）
            </label>
            <label>
              共同权重方法
              <select
                value={current.indicators[0]?.weight_method ?? "manual"}
                disabled={!current.indicators.length}
                onChange={(event) =>
                  change(
                    setWeightMethod(
                      current,
                      event.target
                        .value as IndicatorDefinition["weight_method"],
                    ),
                  )
                }
              >
                <option value="manual">手工权重</option>
                <option value="equal">等权</option>
                <option value="entropy">熵权（全时段共同估计）</option>
              </select>
            </label>
          </div>
          <p>
            示范分类仅供参考，不是唯一评价体系：
            {categories.data?.categories.join("、") ?? "读取中"}。
          </p>
          <datalist id="indicator-categories">
            {categories.data?.categories.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </Panel>
        {current.indicators.map((item, index) => (
          <Panel key={item.indicator_id} title={`指标 ${index + 1}`}>
            <fieldset className="scene-form" aria-label={`指标 ${index + 1}`}>
              <div className="form-grid">
                <label>
                  指标名称
                  <input
                    value={item.name}
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        name: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  分类
                  <input
                    list="indicator-categories"
                    value={item.category}
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        category: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  输出单位
                  <input
                    value={item.unit}
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        unit: event.target.value,
                      })
                    }
                  />
                </label>
                <label>
                  指标方向
                  <select
                    value={item.direction}
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        direction: event.target
                          .value as IndicatorDefinition["direction"],
                      })
                    }
                  >
                    <option value="positive">越高越好</option>
                    <option value="negative">越低越好</option>
                  </select>
                </label>
                <label>
                  参考下界
                  <input
                    type="number"
                    step="any"
                    value={
                      Number.isFinite(item.normalization.lower)
                        ? item.normalization.lower
                        : ""
                    }
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        normalization: {
                          ...item.normalization,
                          lower: event.target.valueAsNumber,
                        },
                      })
                    }
                  />
                </label>
                <label>
                  参考上界
                  <input
                    type="number"
                    step="any"
                    value={
                      Number.isFinite(item.normalization.upper)
                        ? item.normalization.upper
                        : ""
                    }
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        normalization: {
                          ...item.normalization,
                          upper: event.target.valueAsNumber,
                        },
                      })
                    }
                  />
                </label>
                {item.weight_method === "manual" ? (
                  <label>
                    手工权重
                    <input
                      type="number"
                      min={0}
                      step="any"
                      value={
                        item.weight !== null && Number.isFinite(item.weight)
                          ? item.weight
                          : ""
                      }
                      onChange={(event) =>
                        editIndicator(index, {
                          ...item,
                          weight: event.target.valueAsNumber,
                        })
                      }
                    />
                  </label>
                ) : (
                  <p>
                    权重由{item.weight_method === "equal" ? "等权" : "熵权"}
                    计算，未运行前不填造数值。
                  </p>
                )}
                <label>
                  指标公式
                  <input
                    value={item.formula}
                    onChange={(event) =>
                      editIndicator(index, {
                        ...item,
                        formula: event.target.value,
                      })
                    }
                  />
                </label>
              </div>
              <p>
                输入先转换到基础单位。加减与比较中的数值常量使用基础单位；归一化边界使用输出单位。超出边界会阻断。
              </p>
              {Object.entries(item.source).map(([alias, column]) => (
                <div className="toolbar" key={alias}>
                  <label>
                    公式输入 {alias} 对应的数据列
                    <input
                      value={column ?? ""}
                      onChange={(event) =>
                        editIndicator(index, {
                          ...item,
                          source: {
                            ...item.source,
                            [alias]: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <button
                    disabled={Object.keys(item.source).length === 1}
                    onClick={() =>
                      editIndicator(index, {
                        ...item,
                        source: Object.fromEntries(
                          Object.entries(item.source).filter(
                            ([key]) => key !== alias,
                          ),
                        ),
                      })
                    }
                  >
                    移除输入 {alias}
                  </button>
                </div>
              ))}
              <div className="toolbar">
                <button
                  className="secondary"
                  onClick={() => {
                    let alias = "input2";
                    let number = 2;
                    while (alias in item.source) alias = `input${++number}`;
                    editIndicator(index, {
                      ...item,
                      source: { ...item.source, [alias]: "" },
                    });
                  }}
                >
                  添加公式输入
                </button>
                <button
                  className="danger"
                  onClick={() =>
                    change({
                      ...current,
                      indicators: current.indicators.filter(
                        (_, i) => i !== index,
                      ),
                    })
                  }
                >
                  删除指标 {index + 1}
                </button>
              </div>
            </fieldset>
          </Panel>
        ))}
        <div className="toolbar">
          <button
            className="secondary"
            onClick={() => {
              const indicator = freshIndicator();
              const method = current.indicators[0]?.weight_method ?? "manual";
              change({
                ...current,
                indicators: [
                  ...current.indicators,
                  {
                    ...indicator,
                    weight_method: method,
                    weight: method === "manual" ? NaN : null,
                  },
                ],
              });
            }}
          >
            添加指标
          </button>
          <button onClick={() => save.mutate()}>保存指标体系版本</button>
          {id ? (
            <button className="secondary" onClick={() => archive.mutate()}>
              归档指标体系
            </button>
          ) : null}
        </div>
      </fieldset>
      <Panel title="分级阈值">
        <p>得分在 0–1 范围；边界值进入更高一级。</p>
        {current.class_breaks.map((value, index) => (
          <label key={index}>
            阈值 {index + 1}
            <input
              disabled={historical || busy}
              type="number"
              step="any"
              value={Number.isFinite(value) ? value : ""}
              onChange={(event) =>
                change({
                  ...current,
                  class_breaks: current.class_breaks.map((item, i) =>
                    i === index ? event.target.valueAsNumber : item,
                  ),
                })
              }
            />
          </label>
        ))}
      </Panel>
      {id && !historical ? (
        <Panel title="准备评价输入">
          <p>
            从已校验的 JSON
            指标观测中计算公式，保存带有体系与观测版本来源的新文件。保存未完成的编辑后才能准备。
          </p>
          <div className="toolbar">
            <label>
              搜索观测数据
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <button disabled={busy} onClick={() => setLookup(search.trim())}>
              搜索观测
            </button>
          </div>
          <label>
            观测数据
            <select
              disabled={busy}
              value={dataId}
              onChange={(event) => {
                const selected = assets.data?.find(
                  (row) => row.id === event.target.value,
                );
                selectInput(event.target.value, selected?.version ?? 1);
              }}
            >
              <option value="">选择实际观测文件</option>
              {assets.data?.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · v{row.version}
                </option>
              ))}
            </select>
          </label>
          <label>
            观测版本
            <input
              disabled={busy}
              type="number"
              min={1}
              step={1}
              value={Number.isFinite(dataVersion) ? dataVersion : ""}
              onChange={(event) =>
                selectInput(dataId, event.target.valueAsNumber)
              }
            />
          </label>
          <button
            disabled={
              busy ||
              draft !== null ||
              !dataId ||
              !Number.isInteger(dataVersion) ||
              dataVersion < 1
            }
            onClick={() => prepared.mutate()}
          >
            准备固定版本输入
          </button>
          {prepared.data ? (
            <div role="status">
              <p>
                已准备：{prepared.data.spec.name} · v{prepared.data.version}
              </p>
              <Link
                to={`/data/${encodeURIComponent(prepared.data.resource_id)}/workspace`}
              >
                查看实际文件与质量
              </Link>
              <p>后续工作流将固定本体系的权重方法。</p>
              <FrameworkPlanning
                key={prepared.data.resource_id}
                projectId={projectId}
                frameworkId={id}
                frameworkVersion={base!.version}
                dataId={prepared.data.resource_id}
                dataVersion={prepared.data.version}
              />
            </div>
          ) : null}
        </Panel>
      ) : null}
    </>
  );
}
