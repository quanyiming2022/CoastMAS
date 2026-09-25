const labels: Record<string, string> = {
  benefit: "效益",
  cost: "成本",
  area: "面积",
  ecological_cost: "生态代价",
  risk: "风险",
};
export const emptyOptimization = {
  task: "optimization",
  method: "binary_allocation",
  quantities: Object.fromEntries(
    Object.keys(labels).map((key) => [key, { concept: "", unit: "" }]),
  ),
  protected_concept: "",
  risk_aggregation: "additive_index",
  additivity_basis: "",
  budget: null,
  minimum_area: null,
  maximum_ecological_cost: null,
  maximum_risk: null,
  time_limit: 30,
};
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export function OptimizationRules({
  configuration,
  change,
}: {
  configuration: Record<string, unknown>;
  change: (configuration: Record<string, unknown>) => void;
}) {
  const quantities = object(configuration.quantities);
  function patch(key: string, value: unknown) {
    change({ ...configuration, [key]: value });
  }
  function quantity(key: string, field: string, value: string) {
    patch("quantities", {
      ...quantities,
      [key]: { ...object(quantities[key]), [field]: value },
    });
  }
  return (
    <>
      <div className="section-heading">
        <h3>候选单元变量</h3>
      </div>
      <table className="method-indicators">
        <thead>
          <tr>
            <th>用途</th>
            <th>指标科学含义</th>
            <th>单位</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(labels).map(([key, label]) => (
            <tr key={key}>
              <th>{label}</th>
              <td>
                <input
                  aria-label={`${label}指标`}
                  value={String(object(quantities[key]).concept ?? "")}
                  onChange={(e) => quantity(key, "concept", e.target.value)}
                />
              </td>
              <td>
                <input
                  aria-label={`${label}单位`}
                  value={String(object(quantities[key]).unit ?? "")}
                  onChange={(e) => quantity(key, "unit", e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="method-form-grid">
        <label>
          保护标记含义
          <input
            value={String(configuration.protected_concept ?? "")}
            onChange={(e) => patch("protected_concept", e.target.value)}
          />
        </label>
        <label>
          求解时限（秒）
          <input
            type="number"
            min="1"
            max="120"
            value={Number(configuration.time_limit ?? 30)}
            onChange={(e) =>
              patch(
                "time_limit",
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
          />
        </label>
        {Object.entries({
          budget: "总预算",
          minimum_area: "最小面积",
          maximum_ecological_cost: "生态代价上限",
          maximum_risk: "风险上限",
        }).map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              type="number"
              step="any"
              min="0"
              value={
                typeof configuration[key] === "number"
                  ? (configuration[key] as number)
                  : ""
              }
              onChange={(e) =>
                patch(
                  key,
                  e.target.value === "" ? null : Number(e.target.value),
                )
              }
            />
          </label>
        ))}
        <label className="method-basis">
          风险可加性依据
          <textarea
            rows={2}
            value={String(configuration.additivity_basis ?? "")}
            onChange={(e) => patch("additivity_basis", e.target.value)}
          />
        </label>
      </div>
      <p>请填写有依据的约束；未知值留空，不能当作零。</p>
    </>
  );
}
