import { lazy, Suspense, useMemo, useState } from "react";
import { z } from "zod";
import { DataTable, Loading } from "./components";
import type { GeographicCollection } from "./result-data";
const GeoMap = lazy(() => import("./GeoMap"));
export const projectionResult = z
  .object({
    method: z.enum(["PPCI::mcdc", "pprRFA::zppr.numeric"]),
    row_ids: z.array(z.string()).min(4).max(10000),
    cluster: z.array(z.number().int().positive()).optional(),
    fitted: z.array(z.number()).optional(),
    residuals: z.array(z.number()).optional(),
    response_unit: z.string().optional(),
    locations: z
      .array(
        z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)]),
      )
      .nullable(),
    observation_scope: z
      .enum(["sample_only", "all_joint_valid_cells"])
      .nullable(),
    joint_valid_cells: z.number().int().nonnegative().nullable(),
    business_validated: z.literal(false),
  })
  .refine(
    (value) =>
      (value.method === "PPCI::mcdc"
        ? value.cluster?.length === value.row_ids.length
        : value.fitted?.length === value.row_ids.length &&
          value.residuals?.length === value.row_ids.length) &&
      (!value.locations || value.locations.length === value.row_ids.length),
  );
export default function ProjectionResultView({
  result,
}: {
  result: z.infer<typeof projectionResult>;
}) {
  const [page, setPage] = useState(0);
  const cluster = result.method === "PPCI::mcdc";
  const data = useMemo<GeographicCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        result.locations?.map((coordinates, index) => ({
          type: "Feature",
          id: result.row_ids[index],
          geometry: { type: "Point", coordinates },
          properties: {
            name: result.row_ids[index],
            value: cluster ? result.cluster?.[index] : result.fitted?.[index],
          },
        })) ?? [],
    }),
    [result, cluster],
  );
  return (
    <>
      <p>
        {result.observation_scope === "sample_only"
          ? "仅样本结果，不代表全图分类或全图预测。"
          : result.observation_scope === "all_joint_valid_cells"
            ? "全部共同有效像元结果；排除的缺测区域没有结果。"
            : "技术验证结果，未声明空间覆盖范围。"}{" "}
        本次共{result.row_ids.length}个观测；共同有效像元总数：
        {result.joint_valid_cells ?? "未提供"}。
      </p>
      <p>
        {cluster
          ? "聚类编号只表示相似性分组，没有好坏等级含义。"
          : `回归为训练样本拟合，尚非独立验证或未来预测；响应单位：${result.response_unit}。`}{" "}
        正式业务解释仍需核验。
      </p>
      {data.features.length ? (
        <Suspense fallback={<Loading />}>
          <GeoMap data={data} label="投影寻踪观测位置地图" />
        </Suspense>
      ) : null}
      <DataTable>
        <thead>
          <tr>
            <th>原始像元行列号</th>
            <th>{cluster ? "聚类编号" : "拟合值"}</th>
            {!cluster ? <th>残差（观测－拟合）</th> : null}
            <th>经度</th>
            <th>纬度</th>
          </tr>
        </thead>
        <tbody>
          {result.row_ids
            .slice(page * 20, (page + 1) * 20)
            .map((id, offset) => {
              const index = page * 20 + offset;
              return (
                <tr key={id}>
                  <td>{id}</td>
                  <td>
                    {cluster ? result.cluster?.[index] : result.fitted?.[index]}
                  </td>
                  {!cluster ? <td>{result.residuals?.[index]}</td> : null}
                  <td>{result.locations?.[index]?.[0] ?? "未提供"}</td>
                  <td>{result.locations?.[index]?.[1] ?? "未提供"}</td>
                </tr>
              );
            })}
        </tbody>
      </DataTable>
      <div className="pagination">
        <button
          type="button"
          disabled={page === 0}
          onClick={() => setPage(page - 1)}
        >
          上一页观测
        </button>
        <span>
          第{page + 1}页 / {Math.ceil(result.row_ids.length / 20)}页 · 共
          {result.row_ids.length}项
        </span>
        <button
          type="button"
          disabled={(page + 1) * 20 >= result.row_ids.length}
          onClick={() => setPage(page + 1)}
        >
          下一页观测
        </button>
      </div>
      <p>页面顶部“下载完整结果”包含全部观测、模型与源资产版本。</p>
    </>
  );
}
