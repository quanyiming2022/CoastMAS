import type { Asset } from "./api";
import type { Draft } from "./draft";
export function IndicatorBindings({
  draft,
  assets,
  edit,
}: {
  draft: Draft;
  assets: Asset[];
  edit: (change: (draft: Draft) => Draft) => void;
}) {
  if (!draft.mapping.length)
    return <p>添加资料后可选择已有指标或按配方生成。</p>;
  const patch = (index: number, change: Partial<Draft["mapping"][number]>) =>
    edit((d) => ({
      ...d,
      mapping: d.mapping.map((m, i) => (i === index ? { ...m, ...change } : m)),
    }));
  return (
    <section aria-label="指标装配">
      <h3>已有指标</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>资料与字段</th>
              <th>用途</th>
              <th>指标含义</th>
              <th>原始单位</th>
              <th>评价单元</th>
            </tr>
          </thead>
          <tbody>
            {draft.mapping.map((m, index) => (
              <tr key={m.asset_id + ":" + m.field}>
                <td>
                  <span>
                    {assets.find((a) => a.id === m.asset_id)?.name ??
                      "资料待读取"}
                  </span>
                  <details>
                    <summary>来源字段</summary>
                    {m.field}
                  </details>
                </td>
                <td>
                  <select
                    aria-label={`用途 ${m.field}`}
                    value={m.role}
                    onChange={(e) =>
                      patch(index, { role: e.target.value as typeof m.role })
                    }
                  >
                    <option value="feature">计算指标</option>
                    {draft.purpose === "regression" || m.role === "response" ? (
                      <option value="response">响应变量</option>
                    ) : null}
                    <option value="identity">观测标识</option>
                    <option value="ignored">不参与计算</option>
                    {["time", "geometry", "constraint"].includes(m.role) ? (
                      <option value={m.role}>
                        {
                          {
                            time: "时间",
                            geometry: "几何",
                            constraint: "约束",
                          }[m.role as "time"]
                        }
                      </option>
                    ) : null}
                  </select>
                </td>
                <td>
                  <input
                    aria-label={`科学含义 ${m.field}`}
                    disabled={
                      !["feature", "response", "constraint"].includes(m.role)
                    }
                    value={m.concept ?? ""}
                    onChange={(e) =>
                      patch(index, { concept: e.target.value || null })
                    }
                  />
                </td>
                <td>
                  <input
                    aria-label={`单位 ${m.field}`}
                    disabled={!["feature", "response"].includes(m.role)}
                    value={m.unit ?? ""}
                    onChange={(e) =>
                      patch(index, { unit: e.target.value || null })
                    }
                  />
                </td>
                <td>
                  <select
                    aria-label={`支撑 ${m.field}`}
                    value={m.support ?? ""}
                    onChange={(e) =>
                      patch(index, { support: e.target.value || null })
                    }
                  >
                    <option value="">待确定</option>
                    <option value="grid">栅格像元</option>
                    <option value="management_unit">管理单元</option>
                    <option value="point">观测点</option>
                    <option value="interval">时间区间</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
