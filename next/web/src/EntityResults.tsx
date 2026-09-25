import { lazy, Suspense, useMemo, useState } from "react";
import type { FeatureCollection, Geometry } from "geojson";
import { z } from "zod";
const VectorMap = lazy(() => import("./VectorMap"));
const geometry = z.custom<Geometry>(
  (value) =>
    !!value &&
    typeof value === "object" &&
    "type" in value &&
    [
      "Point",
      "MultiPoint",
      "LineString",
      "MultiLineString",
      "Polygon",
      "MultiPolygon",
      "GeometryCollection",
    ].includes(String(value.type)),
);
export const collectionSchema = z.object({
  type: z.literal("FeatureCollection"),
  theme_property: z.string().optional(),
  features: z.array(
    z.object({
      type: z.literal("Feature"),
      id: z.string(),
      properties: z.record(z.string(), z.json()).nullable(),
      geometry,
    }),
  ),
});
const geometryNames: Record<string, string> = {
  Point: "点",
  MultiPoint: "多点",
  LineString: "线",
  MultiLineString: "多线",
  Polygon: "面",
  MultiPolygon: "多面",
  GeometryCollection: "几何集合",
};
function value(item: unknown) {
  if (item === null || item === undefined) return "缺值";
  if (item === "") return "空文本";
  if (typeof item === "boolean") return item ? "是" : "否";
  if (typeof item === "object")
    return (
      <details className="disclosure">
        <summary>查看复合属性</summary>
        <pre>{JSON.stringify(item, null, 2)}</pre>
      </details>
    );
  return String(item);
}
export function EntityResults({
  data,
  tableOnly = false,
}: {
  data: unknown;
  tableOnly?: boolean;
}) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [showMap, setShowMap] = useState(true);
  const parsed = useMemo(() => collectionSchema.safeParse(data), [data]);
  const columns = useMemo(
    () =>
      parsed.success
        ? [
            ...new Set(
              parsed.data.features.flatMap((feature) =>
                Object.keys(feature.properties ?? {}),
              ),
            ),
          ]
        : [],
    [parsed],
  );
  if (!parsed.success)
    return (
      <p role="alert" className="error">
        实体成果结构不完整，无法安全展示；请下载原始成果核对。
      </p>
    );
  const features = parsed.data.features;
  if (new Set(features.map((feature) => feature.id)).size !== features.length)
    return (
      <p role="alert" className="error">
        实体标识重复，不能把属性与地图错误关联。
      </p>
    );
  if (!features.length) return <p>没有地理实体</p>;
  const pages = Math.ceil(features.length / 25),
    current = Math.min(page, pages - 1);
  function choose(id: string) {
    setSelected(id);
    setShowMap(true);
    const index = features.findIndex((feature) => feature.id === id);
    if (index >= 0) setPage(Math.floor(index / 25));
  }
  return (
    <section className="entity-results">
      {!tableOnly ? (
        <>
          <h3>地理实体成果</h3>
          <p>
            实际实体 {features.length.toLocaleString()} 个 · 坐标为WGS
            84经纬度。属性保留源值，未补写科学含义。
          </p>
          <button
            type="button"
            className="secondary"
            onClick={() => setShowMap(!showMap)}
          >
            {showMap ? "收起实体地图" : "查看实体地图"}
          </button>
          {showMap ? (
            <Suspense fallback={<p role="status">正在加载实体地图…</p>}>
              <VectorMap
                data={parsed.data as FeatureCollection<Geometry>}
                themeProperty={parsed.data.theme_property}
                selected={selected}
                onSelect={choose}
              />
            </Suspense>
          ) : null}
          {selected !== null ? <p role="status">当前选择：{selected}</p> : null}
        </>
      ) : null}
      <div className="table-scroll">
        <table aria-label="完整实体属性">
          <thead>
            <tr>
              <th>实体标识</th>
              <th>几何类型</th>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {features.slice(current * 25, current * 25 + 25).map((feature) => (
              <tr key={feature.id} aria-selected={selected === feature.id}>
                <td>{feature.id}</td>
                <td>{geometryNames[feature.geometry.type]}</td>
                {columns.map((column) => (
                  <td
                    key={column}
                    className={
                      typeof feature.properties?.[column] === "number"
                        ? "numeric"
                        : undefined
                    }
                  >
                    {value(feature.properties?.[column])}
                  </td>
                ))}
                <td>
                  <button
                    type="button"
                    className="secondary"
                    aria-label={`在地图定位 ${feature.id}`}
                    aria-pressed={selected === feature.id}
                    onClick={() => choose(feature.id)}
                  >
                    在地图定位
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>
          {current + 1} / {pages} 页 · 共 {features.length} 条
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
      <p>
        地图点选与表格定位联动。下载成果包包含全部实体的GeoJSON和原始来源，不受当前页影响。
      </p>
    </section>
  );
}
