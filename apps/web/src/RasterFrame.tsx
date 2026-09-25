import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema, revisionSchema } from "./api";
import { contract } from "./contracts";
import { DataTable, ErrorNotice, PageTitle, Panel } from "./components";
import { useWorkspace } from "./workspace";

type Feature = {
  asset_id: string;
  version: number;
  assetName: string;
  name: string;
  unit: string;
  band: number;
};
const prepared = revisionSchema.extend({ spec: contract("DataAssetSpec") });
export default function RasterFrame() {
  const { projectId } = useWorkspace();
  return <Preparation key={projectId} projectId={projectId} />;
}
function Preparation({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [features, setFeatures] = useState<Feature[]>([]);
  const [name, setName] = useState("");
  const [mode, setMode] = useState("all");
  const [sampleSize, setSampleSize] = useState(1000);
  const [seed, setSeed] = useState(42);
  const [standardize, setStandardize] = useState(false);
  const [response, setResponse] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [timeResolution, setTimeResolution] = useState("");
  const query = useQuery({
    queryKey: ["raster-frame-assets", projectId, search, page],
    queryFn: ({ signal }) =>
      request(
        `/data-assets/search?${new URLSearchParams({ project_id: projectId, data_type: "raster", q: search, limit: "20", offset: String(page * 20) })}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const add = useMutation({
    mutationFn: (asset: { id: string; version: number }) =>
      request(
        `/data-assets/${encodeURIComponent(asset.id)}?version=${asset.version}`,
        prepared,
      ),
    onSuccess: ({ spec }) => {
      const declared = spec.quality.declarations;
      const unit =
        declared &&
        typeof declared === "object" &&
        !Array.isArray(declared) &&
        "value_unit" in declared &&
        typeof declared.value_unit === "string"
          ? declared.value_unit
          : "";
      const variable =
        spec.variables.length === 1 ? spec.variables[0] : undefined;
      setFeatures((current) => [
        ...current,
        {
          asset_id: spec.id,
          version: spec.version,
          assetName: spec.name,
          name: variable?.name ?? "",
          unit: variable?.unit ?? unit,
          band: 1,
        },
      ]);
    },
  });
  const create = useMutation({
    mutationFn: () =>
      request("/data-assets/prepare-raster-frame", prepared, {
        method: "POST",
        body: {
          project_id: projectId,
          name,
          ...(start || end || timeResolution
            ? {
                period: {
                  start: `${start}T00:00:00Z`,
                  end: `${end}T00:00:00Z`,
                },
                time_resolution: timeResolution,
              }
            : {}),
          features: features.map(({ asset_id, version, name, unit, band }) => ({
            asset_id,
            version,
            name,
            unit,
            band,
          })),
          options: {
            mode,
            standardize,
            ...(mode === "sample" ? { sample_size: sampleSize, seed } : {}),
            ...(response ? { response_index: Number(response) } : {}),
          },
        },
      }),
    onSuccess: (value) =>
      navigate(`/data/${encodeURIComponent(value.spec.id)}/workspace`),
  });
  function update(index: number, patch: Partial<Feature>) {
    setFeatures(
      features.map((feature, current) =>
        current === index ? { ...feature, ...patch } : feature,
      ),
    );
  }
  return (
    <>
      <PageTitle
        title="从影像准备模型输入"
        description="选择已导入资产并声明变量；软件读取实际像元，无需手写矩阵JSON。"
      />
      <ErrorNotice error={query.error ?? create.error ?? add.error} />
      <Panel title="选择来源资产">
        <label>
          搜索已导入影像
          <input
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setPage(0);
            }}
          />
        </label>
        <DataTable>
          <thead>
            <tr>
              <th>资产名称</th>
              <th>版本</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {query.isPending ? (
              <tr>
                <td colSpan={3}>正在读取…</td>
              </tr>
            ) : query.isError ? (
              <tr>
                <td colSpan={3}>读取失败，请重试。</td>
              </tr>
            ) : query.data?.length === 0 ? (
              <tr>
                <td colSpan={3}>没有匹配的影像，请先导入真实影像。</td>
              </tr>
            ) : (
              query.data?.map((asset) => (
                <tr key={asset.id}>
                  <td>{asset.name}</td>
                  <td>{asset.version}</td>
                  <td>
                    <button
                      type="button"
                      disabled={
                        features.length >= 8 ||
                        create.isPending ||
                        add.isPending
                      }
                      onClick={() => add.mutate(asset)}
                    >
                      选择{asset.name}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </DataTable>
        <div className="toolbar">
          <button
            type="button"
            disabled={page === 0 || query.isPending}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span>第{page + 1}页 · 每页最多20项</span>
          <button
            type="button"
            disabled={query.isPending || query.data?.length !== 20}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      </Panel>
      <Panel title="变量与计算范围">
        <p>
          已登记变量或用户确认的单位会自动带入；来源缺失时保持空白，请核对后补充。
        </p>
        <form
          className="form-workspace form-shell"
          onSubmit={(event) => {
            event.preventDefault();
            create.mutate();
          }}
        >
          <label>
            输入资产名称
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {features.map((feature, index) => (
            <fieldset
              className="form-section"
              key={`${feature.asset_id}:${index}`}
            >
              <legend>
                {index + 1}. {feature.assetName} · v{feature.version}
              </legend>
              <div className="form-grid">
                <label>
                  变量名称
                  <input
                    required
                    value={feature.name}
                    onChange={(event) =>
                      update(index, { name: event.target.value })
                    }
                  />
                </label>
                <label>
                  变量单位
                  <input
                    required
                    placeholder="例如 m；无量纲为1，请勿猜填"
                    value={feature.unit}
                    onChange={(event) =>
                      update(index, { unit: event.target.value })
                    }
                  />
                </label>
                <label>
                  读取波段
                  <input
                    type="number"
                    min={1}
                    required
                    value={feature.band}
                    onChange={(event) =>
                      update(index, { band: Number(event.target.value) })
                    }
                  />
                </label>
                <button
                  type="button"
                  disabled={create.isPending}
                  onClick={() => {
                    setFeatures(
                      features.filter((_, current) => current !== index),
                    );
                    setResponse("");
                  }}
                >
                  移除此变量
                </button>
              </div>
            </fieldset>
          ))}
          <div className="form-grid">
            <label>
              数据范围
              <select
                aria-label="数据范围"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
              >
                <option value="all">全部共同有效像元（最多10000个）</option>
                <option value="sample">
                  显式随机样本（结果仅代表所选样本）
                </option>
              </select>
            </label>
            <label>
              回归响应变量
              <select
                aria-label="回归响应变量"
                value={response}
                onChange={(event) => setResponse(event.target.value)}
              >
                <option value="">无（聚类输入）</option>
                {features.map((feature, index) => (
                  <option key={index} value={index}>
                    {feature.name || `变量${index + 1}`}
                  </option>
                ))}
              </select>
            </label>
            {mode === "sample" ? (
              <>
                <label>
                  样本数量上限
                  <input
                    type="number"
                    min={4}
                    max={10000}
                    required
                    value={sampleSize}
                    onChange={(event) =>
                      setSampleSize(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  采样随机种子
                  <input
                    type="number"
                    min={0}
                    max={2147483647}
                    required
                    value={seed}
                    onChange={(event) => setSeed(Number(event.target.value))}
                  />
                </label>
              </>
            ) : null}
          </div>
          <fieldset className="form-section">
            <legend>统计时期声明（可留空；未声明不能通过正式运行预检）</legend>
            <div className="form-grid">
              <label>
                统计时期开始
                <input
                  type="date"
                  value={start}
                  onChange={(event) => setStart(event.target.value)}
                />
              </label>
              <label>
                统计时期结束
                <input
                  type="date"
                  value={end}
                  onChange={(event) => setEnd(event.target.value)}
                />
              </label>
              <label>
                时间支持长度
                <input
                  placeholder="例如 365 day，由资料含义确定"
                  value={timeResolution}
                  onChange={(event) => setTimeResolution(event.target.value)}
                />
              </label>
            </div>
          </fieldset>
          <label>
            <input
              type="checkbox"
              checked={standardize}
              onChange={(event) => setStandardize(event.target.checked)}
            />
            模型运行时按所选样本均值和标准差标准化
          </label>
          <p>
            仅合并坐标系、尺寸和像元位置一致的影像；缺测使用共同有效区域，并保存总量、排除数量和原始行列号。变量单位是您的科学声明。准备输入不代表正式评价或业务结论已获验证；时间、指标含义及模型适用性仍需核实。
          </p>
          <button
            type="submit"
            disabled={create.isPending || features.length === 0}
          >
            {create.isPending
              ? "正在分块读取与登记…"
              : "生成可用于模型的输入资产"}
          </button>
        </form>
      </Panel>
    </>
  );
}
