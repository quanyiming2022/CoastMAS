import { useState } from "react";
import { z } from "zod";
const schema = z.object({
  comparable: z.boolean(),
  basis: z.string(),
  mode: z.string(),
  differences: z.array(
    z.object({ field: z.string(), left: z.json(), right: z.json() }),
  ),
  adaptations: z.array(
    z.object({ from_unit: z.string(), to_unit: z.string() }),
  ),
  inputs: z.array(
    z.object({
      job_id: z.string(),
      title: z.string(),
      draft_revision: z.number(),
      sha256: z.string(),
    }),
  ),
  rows: z.array(
    z.object({
      id: z.string(),
      left: z.union([z.number(), z.boolean()]),
      right: z.union([z.number(), z.boolean()]),
      difference: z.number(),
      unit: z.string(),
      difference_unit: z.string().optional(),
    }),
  ),
});
const names: Record<string, string> = {
  weights: "指标权重",
  budget: "预算",
  minimum_area: "最小面积",
  maximum_ecological_cost: "生态代价上限",
  maximum_risk: "风险上限",
  time_limit: "求解时间上限",
  method: "方法",
  scope: "成果范围",
};
function text(value: z.infer<typeof z.json>): string {
  if (value === null) return "未提供";
  if (Array.isArray(value)) return value.map(text).join("、");
  if (typeof value === "object")
    return Object.entries(value)
      .map(([k, v]) => `${names[k] ?? k}：${text(v)}`)
      .join("；");
  return String(value);
}
function valueText(value: number | boolean) {
  return typeof value === "boolean"
    ? value
      ? "已选"
      : "未选"
    : Number.isInteger(value)
      ? String(value)
      : value.toPrecision(7);
}
export function ComparisonResult({ data }: { data: unknown }) {
  const [page, setPage] = useState(0);
  const parsed = schema.safeParse(data);
  if (!parsed.success)
    return <p role="alert">比较成果结构不完整，不能显示错配结果。</p>;
  const result = parsed.data;
  if (!result.comparable)
    return <p role="alert">成果不具备可比性，不能显示数值差异。</p>;
  const pages = Math.max(1, Math.ceil(result.rows.length / 25));
  const current = Math.min(page, pages - 1);
  return (
    <section aria-label="成果比较结果">
      <h3>成果比较结果</h3>
      <p>{result.basis}</p>
      <p>
        差值方向：对照减基准。比较不修改历史成果，不批准正式业务或政策结论。
      </p>
      {result.inputs.length === 2 ? (
        <ul>
          {result.inputs.map((input, index) => (
            <li key={input.job_id}>
              {index === 0 ? "基准" : "对照"}：{input.title} · v
              {input.draft_revision} ·{" "}
              <a href={`/api/jobs/${input.job_id}/download`}>下载原成果</a>
              <details>
                <summary>固定成果校验码</summary>
                <code className="hash-text">{input.sha256}</code>
              </details>
            </li>
          ))}
        </ul>
      ) : null}
      {result.adaptations.map((a) => (
        <p key={`${a.from_unit}-${a.to_unit}`}>
          自动单位转换：{a.from_unit} → {a.to_unit}（保留转换记录）
        </p>
      ))}
      {result.differences.length ? (
        <div className="table-scroll">
          <table aria-label="方法及条件差异">
            <thead>
              <tr>
                <th>条件</th>
                <th>基准</th>
                <th>对照</th>
              </tr>
            </thead>
            <tbody>
              {result.differences.map((d) => (
                <tr key={d.field}>
                  <th>{names[d.field] ?? d.field}</th>
                  <td>{text(d.left)}</td>
                  <td>{text(d.right)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>核对的资料、方法及条件一致。</p>
      )}
      <div className="table-scroll">
        <table aria-label="逐项比较">
          <thead>
            <tr>
              <th>观测或单元标识</th>
              <th className="numeric">基准</th>
              <th className="numeric">对照</th>
              <th className="numeric">差异</th>
              <th>单位</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.slice(current * 25, current * 25 + 25).map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td className="numeric">{valueText(row.left)}</td>
                <td className="numeric">{valueText(row.right)}</td>
                <td className="numeric">
                  {row.unit === "selection"
                    ? row.difference === 0
                      ? "选择未变"
                      : row.difference > 0
                        ? "新增选择"
                        : "取消选择"
                    : valueText(row.difference)}
                </td>
                <td>
                  {row.unit === "selection" ? "单元选择" : row.unit}
                  {row.difference_unit
                    ? `（差异：${row.difference_unit}）`
                    : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span>
          {current + 1} / {pages} 页 · 共 {result.rows.length} 条
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
    </section>
  );
}
