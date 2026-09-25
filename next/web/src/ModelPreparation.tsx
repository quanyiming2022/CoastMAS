import type { Draft } from "./draft";

interface Props {
  purpose: "cluster" | "regression";
  raster?: boolean;
  options: Draft["options"];
  change: (key: string, value: boolean | number | string | null) => void;
}

export function ModelPreparation({
  purpose,
  options,
  change,
  raster = false,
}: Props) {
  return (
    <section>
      <h2>模型方法</h2>
      <p>
        {purpose === "cluster"
          ? "使用提供的 PPCI::mcdc 实现；类别编号只表示聚类，不代表风险等级。"
          : "使用提供的 pprRFA::zppr.numeric 实现；训练拟合不等于独立预测验证。"}
      </p>
      <div className="form-grid">
        <label>
          标准化规则
          <select
            value={
              typeof options.standardize === "boolean"
                ? String(options.standardize)
                : ""
            }
            onChange={(event) =>
              change(
                "standardize",
                event.target.value === ""
                  ? null
                  : event.target.value === "true",
              )
            }
          >
            <option value="">选择方法规则</option>
            <option value="false">保留原始量纲数值</option>
            <option value="true">按训练集均值和标准差标准化</option>
          </select>
        </label>
        <label>
          {purpose === "cluster" ? "聚类数量" : "投影项数"}
          <input
            type="number"
            min={purpose === "cluster" ? 2 : 1}
            max={20}
            step={1}
            value={typeof options.size === "number" ? options.size : ""}
            onChange={(event) =>
              change(
                "size",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
          />
        </label>
        <label>
          随机种子
          <input
            type="number"
            min={0}
            max={2147483647}
            step={1}
            value={typeof options.seed === "number" ? options.seed : ""}
            onChange={(event) =>
              change(
                "seed",
                event.target.value === "" ? null : Number(event.target.value),
              )
            }
          />
        </label>
      </div>
      {raster ? (
        <div className="form-grid">
          <label>
            训练范围
            <select
              value={
                typeof options.training_scope === "string"
                  ? options.training_scope
                  : ""
              }
              onChange={(event) => {
                change("training_scope", event.target.value);
                if (event.target.value === "all") change("sample_size", null);
              }}
            >
              <option value="">选择训练范围</option>
              <option value="all">全部共同有效像元（需符合内存预算）</option>
              <option value="sample">从整个范围均匀抽样，只训练一次</option>
            </select>
          </label>
          {options.training_scope === "sample" ? (
            <label>
              训练样本数
              <input
                type="number"
                min={4}
                max={10000}
                value={
                  typeof options.sample_size === "number"
                    ? options.sample_size
                    : ""
                }
                onChange={(event) =>
                  change(
                    "sample_size",
                    event.target.value === ""
                      ? null
                      : Number(event.target.value),
                  )
                }
              />
            </label>
          ) : null}
          <label>
            成果范围
            <select
              value={
                typeof options.application_scope === "string"
                  ? options.application_scope
                  : ""
              }
              onChange={(event) =>
                change("application_scope", event.target.value)
              }
            >
              <option value="">选择应用范围</option>
              <option value="sample">仅训练观测</option>
              <option value="full">用固定模型应用到完整影像</option>
            </select>
          </label>
          <p>
            全域应用保持同一训练模型和标准化参数，不逐块重训。样本训练不等于全部像元参与训练。
          </p>
        </div>
      ) : null}
      <p>
        从下方实际字段中选择解释变量；回归另需唯一响应变量。标识列无需补填科学单位。
      </p>
    </section>
  );
}
