import { useState } from "react";
import type { JsonValue } from "./generated/contracts";

function isFieldGroup(value: unknown): value is Record<string, JsonValue> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
const fieldLabels: Record<string, string> = {
  sea_level_baseline_m: "基准海平面（m）",
  vertical_datum: "垂向基准",
  coastal_seeds: "海岸连通起点（行、列）",
  population_distribution: "人口空间分布假设",
  target_grid: "目标栅格",
  crs: "坐标参考系",
  transform: "仿射变换六参数",
  width: "列数",
  height: "行数",
  data_label: "数据性质",
  period_policy: "时期比较规则",
  method_scope: "方法适用范围",
};
export default function ScientificFields({
  values,
  onChange,
  title,
}: {
  values: Record<string, JsonValue>;
  onChange: (value: Record<string, JsonValue>) => void;
  title: string;
}) {
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  return (
    <fieldset className="scientific-fields">
      <legend>{title}</legend>
      {Object.entries(values).map(([key, value]) => (
        <div key={key} className="scientific-field">
          <JsonField
            label={fieldLabels[key] ?? key}
            value={value}
            onChange={(next) => onChange({ ...values, [key]: next })}
          />
          <button
            className="secondary"
            onClick={() => {
              const next = { ...values };
              delete next[key];
              onChange(next);
            }}
          >
            移除 {fieldLabels[key] ?? key}
          </button>
        </div>
      ))}
      <div className="toolbar">
        <label>
          {title}新增字段名
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <button
          className="secondary"
          onClick={() => {
            const key = name.trim();
            if (
              !key ||
              key in values ||
              ["__proto__", "constructor", "prototype"].includes(key)
            ) {
              setError("字段名不能为空或重复");
              return;
            }
            onChange({ ...values, [key]: null });
            setName("");
            setError("");
          }}
        >
          添加{title}字段
        </button>
      </div>
      {error ? <p role="alert">{error}</p> : null}
    </fieldset>
  );
}
function JsonField({
  value,
  label,
  onChange,
}: {
  value: JsonValue;
  label: string;
  onChange: (next: JsonValue) => void;
}) {
  const [kind, setKind] = useState(
    typeof value === "number"
      ? "number"
      : typeof value === "boolean"
        ? "boolean"
        : Array.isArray(value)
          ? "array"
          : value && typeof value === "object"
            ? "object"
            : "string",
  );
  return (
    <div>
      <label>
        {label}类型
        <select
          value={kind}
          onChange={(event) => {
            const next = event.target.value;
            setKind(next);
            onChange(next === "array" ? [] : next === "object" ? {} : null);
          }}
        >
          <option value="string">文字</option>
          <option value="number">数值</option>
          <option value="boolean">是 / 否</option>
          <option value="array">有序列表</option>
          <option value="object">字段组</option>
        </select>
      </label>
      {kind === "array" && Array.isArray(value) ? (
        <fieldset>
          <legend>{label}</legend>
          {value.map((item, index) => (
            <div key={index}>
              <JsonField
                label={`${label} ${index + 1}`}
                value={item}
                onChange={(next) =>
                  onChange(
                    value.map((entry, position) =>
                      position === index ? next : entry,
                    ),
                  )
                }
              />
              <button
                className="secondary"
                onClick={() =>
                  onChange(value.filter((_, position) => position !== index))
                }
              >
                移除{label}第 {index + 1} 项
              </button>
            </div>
          ))}
          <button
            className="secondary"
            onClick={() => onChange([...value, null])}
          >
            添加{label}项
          </button>
        </fieldset>
      ) : null}
      {kind === "object" && isFieldGroup(value) ? (
        <ScientificFields title={label} values={value} onChange={onChange} />
      ) : null}
      {kind === "number" ? (
        <label>
          {label}
          <input
            type="number"
            step="any"
            value={typeof value === "number" ? value : ""}
            onChange={(event) =>
              onChange(
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
          />
        </label>
      ) : null}
      {kind === "string" ? (
        <label>
          {label}
          <input
            value={typeof value === "string" ? value : ""}
            onChange={(event) => onChange(event.target.value)}
          />
        </label>
      ) : null}
      {kind === "boolean" ? (
        <label>
          {label}
          <select
            value={value === true ? "true" : value === false ? "false" : ""}
            onChange={(event) =>
              onChange(
                event.target.value === ""
                  ? null
                  : event.target.value === "true",
              )
            }
          >
            <option value="">未指定</option>
            <option value="true">是</option>
            <option value="false">否</option>
          </select>
        </label>
      ) : null}
    </div>
  );
}
