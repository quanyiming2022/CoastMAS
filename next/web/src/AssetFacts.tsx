import { z } from "zod";
import type { Asset } from "./api";
const rowsSchema = z.array(z.record(z.string(), z.json()));
const issueSchema = z.object({
  code: z.string(),
  message: z.string().optional(),
  layer: z.string().optional(),
});
const labels: Record<string, string> = {
  csvw: "CSVW表格与元数据",
  csv: "分隔符表格",
  geotiff: "GeoTIFF栅格",
  cog: "云优化GeoTIFF",
  netcdf: "NetCDF科学数据",
  geojson: "GeoJSON地理要素",
  geopackage: "GeoPackage空间包",
  shapefile: "Shapefile空间包",
  stac: "STAC资料描述",
};
function value(value: unknown) {
  if (value === null || value === undefined) return "缺值";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return "复合值（完整内容见原始资料）";
  return String(value);
}
export function AssetFacts({
  asset,
  expanded = false,
}: {
  asset: Asset;
  expanded?: boolean;
}) {
  return (
    <details className="disclosure asset-facts" open={expanded}>
      <summary>查看自动读取的内容与质量</summary>
      <p>
        {labels[asset.facts.profile] ?? asset.facts.profile} ·{" "}
        {asset.facts.standard_version ?? "文件未明确声明规范版本"}
      </p>
      <p>
        以下是文件事实；科学定义与用户声明另存。表格预览最多20行，不代表全部记录。
      </p>
      {asset.facts.issues.map((raw, index) => {
        const parsed = issueSchema.safeParse(raw);
        return (
          <p className="warning" key={index}>
            {parsed.success
              ? `${parsed.data.layer ? parsed.data.layer + "：" : ""}${parsed.data.message ?? parsed.data.code}`
              : "存在需要核对的文件质量问题"}
          </p>
        );
      })}
      {asset.facts.layers.map((layer) => {
        const rows = rowsSchema.safeParse(layer.preview);
        return (
          <div key={layer.name}>
            <h3>{layer.name}</h3>
            <p>
              {layer.row_count === null
                ? "记录数量尚未完成核验"
                : `完整记录数：${layer.row_count.toLocaleString()}`}
            </p>
            <div className="table-scroll">
              <table aria-label={`${asset.name} ${layer.name} 字段事实`}>
                <thead>
                  <tr>
                    <th>源字段</th>
                    <th>文件类型</th>
                    <th>文件单位</th>
                    <th>文件语义</th>
                  </tr>
                </thead>
                <tbody>
                  {layer.fields.map((field) => (
                    <tr key={field.name}>
                      <td>{field.name}</td>
                      <td>{field.data_type}</td>
                      <td>{field.unit ?? "未声明"}</td>
                      <td>{field.concept ?? "未声明"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.success && rows.data.length ? (
              <div className="table-scroll">
                <table aria-label={`${asset.name} ${layer.name} 原始内容预览`}>
                  <thead>
                    <tr>
                      {layer.fields.map((field) => (
                        <th key={field.name}>{field.name}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.data.slice(0, 20).map((row, index) => (
                      <tr key={index}>
                        {layer.fields.map((field) => (
                          <td key={field.name}>{value(row[field.name])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        );
      })}
    </details>
  );
}
