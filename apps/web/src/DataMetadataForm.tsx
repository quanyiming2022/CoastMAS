import schema from "../contracts.schema.json";
import type { JsonValue } from "./generated/contracts";
import ScientificFields from "./ScientificFields";
import { modelFieldOptions } from "./model-editor";
import { newDataVariable } from "./data-editor";
export default function DataMetadataForm({
  values,
  onChange,
}: {
  values: Record<string, JsonValue>;
  onChange: (next: Record<string, JsonValue>) => void;
}) {
  const variables = Array.isArray(values.variables) ? values.variables : [];
  function update(key: string, value: JsonValue) {
    onChange({ ...values, [key]: value });
  }
  return (
    <>
      {(
        [
          ["name", "数据名称"],
          ["source", "数据来源"],
          ["license", "许可证"],
        ] as const
      ).map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            value={String(values[key] ?? "")}
            onChange={(event) => update(key, event.target.value)}
          />
        </label>
      ))}
      <label>
        数据类别
        <select
          value={String(values.type)}
          onChange={(event) => update("type", event.target.value)}
        >
          {schema.$defs.DataAssetSpec.properties.type.enum
            .filter((type) => !["service", "database"].includes(type))
            .map((type) => (
              <option key={type}>{type}</option>
            ))}
        </select>
      </label>
      <label>
        文件格式
        <select
          value={String(values.format)}
          onChange={(event) => update("format", event.target.value)}
        >
          {schema.$defs.DataAssetSpec.properties.format.enum
            .filter((format) => !["HTTP", "DATABASE"].includes(format))
            .map((format) => (
              <option key={format}>{format}</option>
            ))}
        </select>
      </label>
      <p>
        未知坐标、范围或时期保持未设置；栅格和矢量必须与实际文件一致。上传最多
        64 MiB。Shapefile 使用包含配套文件的 ZIP。
      </p>
      <ScientificFields
        title="空间与时间声明"
        fixedFields
        values={Object.fromEntries(
          [
            "crs",
            "vertical_datum",
            "spatial_extent",
            "time_start",
            "time_end",
            "time_resolution",
          ].map((key) => [key, values[key] ?? null]),
        )}
        onChange={(next) => onChange({ ...values, ...next })}
      />
      <ScientificFields
        title="变量定义"
        fixedFields
        options={modelFieldOptions}
        values={{ variables }}
        onChange={(next) => update("variables", next.variables!)}
      />
      <button
        className="secondary"
        onClick={() => update("variables", [...variables, newDataVariable()])}
      >
        添加数据变量
      </button>
    </>
  );
}
