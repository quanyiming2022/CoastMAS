import { z } from "zod";
import type { Asset } from "./api";
import type { Draft } from "./draft";
const methodNames: Record<string, string> = {
  mean: "区间加权均值",
  sum: "区间总量",
  min: "区间最小值",
  max: "区间最大值",
  nearest: "最近观测",
  interpolation: "线性插值",
};
export function TemporalEditor({
  draft,
  assets,
  onChange,
}: {
  draft: Draft;
  assets: Asset[];
  onChange: (draft: Draft) => void;
}) {
  const available = assets.flatMap((asset) =>
    (asset.facts.temporal_candidates ?? []).map((item) => ({
      ...item,
      asset_id: asset.id,
    })),
  );
  const value = (name: string) =>
    typeof draft.options[name] === "string" ||
    typeof draft.options[name] === "number"
      ? String(draft.options[name])
      : "";
  const chosen = available.find((item) => item.variable === value("variable"));
  const method = value("method"),
    point = ["nearest", "interpolation"].includes(method);
  const methods = chosen
    ? chosen.cell_method === "point"
      ? ["nearest", "interpolation"]
      : [chosen.method!]
    : [];
  function option(key: string, item: string | number) {
    onChange({ ...draft, options: { ...draft.options, [key]: item } });
  }
  function variable(name: string) {
    const next = available.find((item) => item.variable === name);
    onChange({
      ...draft,
      options: {
        ...draft.options,
        variable: name,
        method: next?.method ?? "",
        output_unit: next?.unit ?? "",
        adaptation_basis: "",
        nearest_tolerance: "",
        nearest_tie: "",
      },
      mapping: draft.mapping.map((binding) => ({
        ...binding,
        role:
          next &&
          binding.asset_id === next.asset_id &&
          binding.field === "dataset/" + name
            ? "feature"
            : "ignored",
      })),
    });
  }
  return (
    <section className="temporal-editor">
      <h2>目标时间尺度</h2>
      {assets.length !== 1 ? (
        <p className="warning">
          本次请选择一个时间序列来源；多资料需要先明确关联。
        </p>
      ) : null}
      {assets.length === 1 && !available.length ? (
        <p className="warning">
          这份资料未识别到可适配的一维CF时间变量，请核对变量与时间坐标。
        </p>
      ) : null}
      <div className="form-grid">
        <label>
          观测变量
          <select
            value={value("variable")}
            onChange={(event) => variable(event.target.value)}
          >
            <option value="">选择实际时间变量</option>
            {available.map((item) => (
              <option key={item.asset_id + item.variable} value={item.variable}>
                {item.variable}
                {item.unit ? ` (${item.unit})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          目标方法
          <select
            value={method}
            onChange={(event) =>
              onChange({
                ...draft,
                options: {
                  ...draft.options,
                  method: event.target.value,
                  adaptation_basis: "",
                },
              })
            }
          >
            <option value="">选择适用方法</option>
            {methods.map((name) => (
              <option key={name} value={name}>
                {methodNames[name]}
              </option>
            ))}
          </select>
        </label>
        {point ? (
          <label>
            目标时刻（源日历）
            <input
              value={value("target")}
              placeholder="YYYY-MM-DD 或 YYYY-MM-DDTHH:MM:SS"
              onChange={(event) => option("target", event.target.value)}
            />
          </label>
        ) : (
          <>
            <label>
              开始日期（源日历）
              <input
                value={value("start")}
                placeholder="YYYY-MM-DD"
                onChange={(event) => option("start", event.target.value)}
              />
            </label>
            <label>
              结束日期（不包含）
              <input
                value={value("end")}
                placeholder="YYYY-MM-DD"
                onChange={(event) => option("end", event.target.value)}
              />
            </label>
          </>
        )}
        <label>
          输出单位
          <input
            value={value("output_unit")}
            onChange={(event) => option("output_unit", event.target.value)}
          />
        </label>
        {method === "nearest" ? (
          <>
            <label>
              容许偏差（
              {chosen?.time_axis_unit.split(" since ")[0] ?? "源时间单位"}）
              <input
                type="number"
                min="0"
                step="any"
                value={value("nearest_tolerance")}
                onChange={(event) =>
                  option(
                    "nearest_tolerance",
                    event.target.value === "" ? "" : Number(event.target.value),
                  )
                }
              />
            </label>
            <label>
              等距时采用
              <select
                value={value("nearest_tie")}
                onChange={(event) => option("nearest_tie", event.target.value)}
              >
                <option value="">遇到等距再决定</option>
                <option value="earlier">较早观测</option>
                <option value="later">较晚观测</option>
              </select>
            </label>
          </>
        ) : null}
      </div>
      {chosen ? (
        <p>
          文件日历：{chosen.calendar} · 文件统计：{chosen.cell_method} ·
          时间轴：{chosen.time_axis_unit}。日期按源日历解释，不自动改成公历。
        </p>
      ) : null}
      {point ? (
        <>
          <label>
            适配依据
            <textarea
              value={value("adaptation_basis")}
              onChange={(event) =>
                option("adaptation_basis", event.target.value)
              }
              aria-describedby="temporal-adaptation-help"
            />
          </label>
          <p id="temporal-adaptation-help">
            目标不等于原始观测时刻时，说明采用近似时间代表或线性变化的依据。依据随本任务保存；不外推，不跳过参与计算的缺测值。
          </p>
        </>
      ) : (
        <p>
          只合并完整的原统计区间。截断区间、缺测或未覆盖目标范围会被预检拦截，不默认补零或假设区间内恒定。
        </p>
      )}
    </section>
  );
}
const temporalResult = z.object({
  variable: z.string(),
  method: z.string(),
  value: z.number(),
  calendar: z.string(),
  observations: z.number(),
  scope: z.string(),
  start: z.string().optional(),
  end: z.string().optional(),
  target: z.string().optional(),
  covered_duration: z.number().optional(),
  duration_unit: z.string().optional(),
  conversion: z.object({ source_unit: z.string(), target_unit: z.string() }),
  adaptation: z.object({ approximate: z.boolean(), basis: z.string() }),
});
export function TemporalResult({ data }: { data: unknown }) {
  const parsed = temporalResult.safeParse(data);
  if (!parsed.success)
    return (
      <p role="alert" className="error">
        时间成果的值、单位或日历不完整，请核对完整成果。
      </p>
    );
  const result = parsed.data;
  return (
    <section aria-label="时间适配成果">
      <h3>时间适配成果</h3>
      <p className="result-number">
        {result.value} {result.conversion.target_unit}
      </p>
      <dl className="temporal-summary">
        <dt>观测变量</dt>
        <dd>{result.variable}</dd>
        <dt>方法</dt>
        <dd>{methodNames[result.method] ?? result.method}</dd>
        <dt>源日历</dt>
        <dd>{result.calendar}</dd>
        {result.target ? (
          <>
            <dt>目标时刻</dt>
            <dd>{result.target}</dd>
          </>
        ) : (
          <>
            <dt>开始（包含）</dt>
            <dd>{result.start}</dd>
            <dt>结束（不包含）</dt>
            <dd>{result.end}</dd>
          </>
        )}
        <dt>单位转换</dt>
        <dd>
          {result.conversion.source_unit} → {result.conversion.target_unit}
        </dd>
      </dl>
      {result.covered_duration !== undefined ? (
        <p>
          实际覆盖 {result.covered_duration} {result.duration_unit} · 使用{" "}
          {result.observations} 条观测
        </p>
      ) : (
        <p>使用 {result.observations} 条实际观测</p>
      )}
      <p className={result.adaptation.approximate ? "warning" : undefined}>
        {result.adaptation.approximate
          ? `近似适配依据：${result.adaptation.basis}`
          : "按完整源支撑或精确源时刻计算，未进行近似时间分配。"}
      </p>
      <p>成果表保留源日历与日期文字，不能将360_day等日期直接按公历解释。</p>
    </section>
  );
}
