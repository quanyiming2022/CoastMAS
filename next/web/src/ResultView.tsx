import { useState } from "react";
import { z } from "zod";
import { resultSchema } from "./api";
import { EntityResults } from "./EntityResults";
import { ComparisonResult } from "./ComparisonResult";
import { TemporalResult } from "./TemporalEditor";
import { VectorResult } from "./VectorResult";
import { ResultArtifact } from "./ResultArtifact";
const observations = z.object({
  row_ids: z.array(z.string()),
  cluster: z.array(z.number()).optional(),
  fitted: z.array(z.number()).optional(),
  residuals: z.array(z.number()).optional(),
  scores: z.array(z.number()).optional(),
  ranks: z.array(z.number()).optional(),
  observation_scope: z.string().optional(),
  joint_valid_cells: z.number().nullable().optional(),
});
const filesSchema = z.array(
  z.object({ name: z.string(), size: z.number(), sha256: z.string() }),
);
const number = (value: number) =>
  Number.isInteger(value) ? String(value) : value.toPrecision(7);
export function ObservationTable({ data }: { data: unknown }) {
  const [page, setPage] = useState(0);
  const parsed = observations.safeParse(data);
  if (!parsed.success) return null;
  const result = parsed.data;
  const columns = (
    ["cluster", "fitted", "residuals", "scores", "ranks"] as const
  ).filter((key) => result[key] !== undefined);
  if (columns.some((key) => result[key]!.length !== result.row_ids.length))
    return (
      <p role="alert" className="error">
        结果列数量与观测身份不一致，不能展示错配结果。
      </p>
    );
  const pages = Math.max(1, Math.ceil(result.row_ids.length / 25));
  const current = Math.min(page, pages - 1);
  const names = {
    cluster: "类别编号",
    fitted: "拟合值",
    residuals: "训练残差",
    scores: "评价得分",
    ranks: "名次",
  };
  return (
    <div>
      <h3>观测结果</h3>
      <p>
        {result.observation_scope === "sample_only"
          ? `训练/观测样本 ${result.row_ids.length} 条；共同有效分母 ${result.joint_valid_cells ?? "未提供"}`
          : `实际观测 ${result.row_ids.length} 条`}
      </p>
      <div className="table-scroll">
        <table aria-label="观测结果">
          <thead>
            <tr>
              <th>观测标识</th>
              {columns.map((key) => (
                <th key={key} className="numeric">
                  {names[key]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.row_ids
              .slice(current * 25, current * 25 + 25)
              .map((id, index) => (
                <tr key={id}>
                  <td>{id}</td>
                  {columns.map((key) => (
                    <td key={key} className="numeric">
                      {number(result[key]![current * 25 + index]!)}
                    </td>
                  ))}
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>
          {current + 1} / {pages} 页 · 共 {result.row_ids.length} 条
        </span>
        <button
          type="button"
          className="secondary"
          disabled={current === 0}
          onClick={() => setPage(current - 1)}
        >
          上一页
        </button>
        <button
          type="button"
          className="secondary"
          disabled={current + 1 === pages}
          onClick={() => setPage(current + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}
const allocationSchema = z.object({
  status: z.string(),
  constraints_satisfied: z.boolean(),
  allocations: z.array(
    z.object({
      id: z.string(),
      selected: z.boolean().nullable(),
      allowed: z.boolean(),
      benefit: z.number(),
      cost: z.number(),
      area: z.number(),
      ecological_cost: z.number(),
      risk: z.number(),
    }),
  ),
});
export function AllocationTable({ data }: { data: unknown }) {
  const [page, setPage] = useState(0);
  const parsed = allocationSchema.safeParse(data);
  if (!parsed.success) return null;
  const { allocations, constraints_satisfied, status } = parsed.data;
  const pages = Math.max(1, Math.ceil(allocations.length / 25)),
    current = Math.min(page, pages - 1);
  return (
    <div>
      <h3>空间配置结果</h3>
      <p>
        {constraints_satisfied
          ? "已形成满足本次约束的工程配置"
          : "尚无满足约束的配置方案"}{" "}
        · 求解状态 {status}
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>单元标识</th>
              <th>配置状态</th>
              <th>保护准入</th>
              {["收益", "成本", "面积（m²）", "生态代价", "风险指数"].map(
                (name) => (
                  <th key={name} className="numeric">
                    {name}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {allocations.slice(current * 25, current * 25 + 25).map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td>
                  {item.selected === null
                    ? "未形成可行解"
                    : item.selected
                      ? "已选入"
                      : "未选入"}
                </td>
                <td>{item.allowed ? "允许配置" : "保护排除"}</td>
                {(
                  [
                    "benefit",
                    "cost",
                    "area",
                    "ecological_cost",
                    "risk",
                  ] as const
                ).map((key) => (
                  <td key={key} className="numeric">
                    {number(item[key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>
          {current + 1} / {pages} 页 · 共 {allocations.length} 个单元
        </span>
        <button
          type="button"
          className="secondary"
          disabled={current === 0}
          onClick={() => setPage(current - 1)}
        >
          上一页
        </button>
        <button
          type="button"
          className="secondary"
          disabled={current + 1 === pages}
          onClick={() => setPage(current + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  );
}

export function ResultView({
  jobId,
  data,
  layerHost,
  currentRevision,
  historical,
}: {
  layerHost?: HTMLElement | null;
  currentRevision?: number;
  historical?: boolean;
  jobId: string;
  data: z.infer<typeof resultSchema>["data"];
}) {
  const files = filesSchema.safeParse(data.files ?? []);
  const application = z
    .object({ predicted_cells: z.number(), application_scope: z.string() })
    .safeParse(data.application);
  if (data.spatial_result && (!files.success || !files.data.some(file=>/\.tiff?$/i.test(file.name)))) {
    return <VectorResult key={jobId} jobId={jobId} data={data.spatial_result} layerHost={layerHost} currentRevision={currentRevision} historical={historical} title={data.operator==="planning_units"?"规划单元":"本次矢量成果"}/>;
  }
  if (files.success && files.data.length > 0) {
    return (
      <ResultArtifact
        key={jobId}
        jobId={jobId}
        layerHost={layerHost}
        currentRevision={currentRevision}
        historical={historical}
        scopeNotice={
          application.success
            ? `应用范围：${application.data.application_scope === "all_predictor_valid_cells" ? "全部解释变量有效像元" : "训练观测"} · ${application.data.predicted_cells} 个`
            : undefined
        }
        supplementary={<ObservationTable key={jobId} data={data} />}
      />
    );
  }
  return (
    <div className="results-view">
      <div className="section-heading">
        <h2>计算结果</h2>
        {data.business_validated !== true ? (
          <span className="warning">工程结果·未业务验证</span>
        ) : null}
      </div>
      {application.success ? (
        <p>
          应用范围：
          {application.data.application_scope === "all_predictor_valid_cells"
            ? "全部解释变量有效像元"
            : "训练观测"}{" "}
          · 已计算 {application.data.predicted_cells.toLocaleString()} 个
        </p>
      ) : null}
      {data.scope === "immutable_result_comparison" ? (
        <ComparisonResult key={`comparison-${jobId}`} data={data} />
      ) : null}
      {data.scope === "declared_interval" ||
      data.scope === "declared_instant" ? (
        <TemporalResult data={data} />
      ) : null}
      {data.spatial_result ? (
        <EntityResults key={`spatial-${jobId}`} data={data.spatial_result} />
      ) : null}
      {data.type === "FeatureCollection" ? (
        <EntityResults key={jobId} data={data} />
      ) : "allocations" in data ? (
        <AllocationTable key={jobId} data={data} />
      ) : (
        <ObservationTable key={jobId} data={data} />
      )}
      <p>
        <a className="button" href={`/api/jobs/${jobId}/bundle`} download>
          下载完整成果包（标准文件与来源）
        </a>
      </p>
      <details>
        <summary>结果范围与来源</summary>
        <p>
          本页显示本次运行的观测结果；样本与全域范围以运行记录为准。来源、方法和验证记录包含在成果包中。
        </p>
      </details>
    </div>
  );
}
