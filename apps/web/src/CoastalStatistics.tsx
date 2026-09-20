import type { z } from "zod";
import type { coastalStatistics } from "./result-data";
import Chart from "./Chart";
export default function CoastalStatistics({
  data,
}: {
  data: z.infer<typeof coastalStatistics>;
}) {
  const units = Object.entries(data.units);
  return (
    <>
      <div className="metrics">
        <div className="metric">
          <span>筛查淹没面积（m²）</span>
          <strong>{data.inundated_area_m2}</strong>
        </div>
        <div className="metric">
          <span>估算受影响人口（人）</span>
          <strong>{data.estimated_affected_population}</strong>
        </div>
        <div className="metric">
          <span>DEM 未知面积（m²）</span>
          <strong>{data.unknown_area_m2}</strong>
        </div>
      </div>
      <p>
        本结果为地形连通筛查，不是水动力模拟。人口估计采用管理单元内均匀分布假设；未知
        DEM 区域不推断为安全或受淹。
      </p>
      <Chart
        labels={units.map(([id]) => id)}
        series={[
          {
            name: "估算受影响人口",
            values: units.map(([, value]) => value.estimated_population),
          },
        ]}
        unit="人"
      />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>管理单元</th>
              <th>受淹面积（m²）</th>
              <th>估算人口（人）</th>
              <th>未知面积（m²）</th>
            </tr>
          </thead>
          <tbody>
            {units.map(([id, value]) => (
              <tr key={id}>
                <td>{id}</td>
                <td>{value.inundated_area_m2}</td>
                <td>{value.estimated_population}</td>
                <td>{value.unknown_area_m2}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="details">
        <summary>计算方法与假设原文</summary>
        <p>{data.method}</p>
        <p>{data.population_assumption}</p>
      </details>
    </>
  );
}
