import { useRef, useState } from "react";
import { z } from "zod";
import { api, jobSchema, type Asset } from "./api";
import type { TaskRecord, Draft } from "./draft";
import { ErrorNotice } from "./shared";
import { record } from "./ResearchStepPanel";
export function ProcessingStep({
  operator,
  task,
  assets,
  edit,
  save,
  onRun,
}: {
  operator: "align_grid" | "ndvi";
  task: TaskRecord;
  assets: Asset[];
  edit: (f: (d: Draft) => Draft) => void;
  save: () => Promise<TaskRecord>;
  onRun: (job: z.infer<typeof jobSchema>) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const pending = useRef<{ fingerprint: string; key: string } | null>(null);
  const rasters = assets.filter((a) =>
    ["geotiff", "cog"].includes(a.facts.profile),
  );
  const settings = record(record(task.draft.options.preparation)[operator]);
  const source =
    rasters.find((a) => a.id === settings.asset_id) ??
    (rasters.length === 1 ? rasters[0] : undefined);
  const patch = (value: Record<string, string | number>) =>
    edit((d) => ({
      ...d,
      options: {
        ...d.options,
        preparation: z
          .json()
          .parse({
            ...record(d.options.preparation),
            [operator]: { ...settings, ...value },
          }),
      },
    }));
  const fields =
    source?.facts.layers
      .flatMap((layer) => layer.fields)
      .filter((f) => /^band_\d+$/.test(f.name)) ?? [];
  const parameters =
    operator === "align_grid"
      ? {
          reference_asset_id:
            settings.reference_asset_id ??
            (rasters.length === 1 ? source?.id : ""),
          quantity_kind: settings.quantity_kind ?? "",
          resampling: settings.resampling ?? "",
        }
      : {
          red_band: settings.red_band ?? 0,
          nir_band: settings.nir_band ?? 0,
          qa_policy: settings.qa_policy ?? "",
        };
  const reference =
    operator === "align_grid"
      ? rasters.find((a) => a.id === parameters.reference_asset_id)
      : undefined;
  async function run() {
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await save();
      const scientific = {
        asset_id: source.id,
        operator,
        band: Number(settings.band ?? 1),
        parameters,
      };
      const fingerprint = JSON.stringify(scientific);
      if (pending.current?.fingerprint !== fingerprint)
        pending.current = { fingerprint, key: crypto.randomUUID() };
      const intent = pending.current.key;
      const node = await api(
        `/tasks/${saved.id}/processing-nodes`,
        z.object({ id: z.string() }),
        {
          method: "POST",
          body: JSON.stringify({
            ...scientific,
            expected_revision: saved.revision,
            idempotency_key: intent,
          }),
        },
      );
      const job = await api(`/processing-nodes/${node.id}/execute`, jobSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: saved.revision,
          idempotency_key: intent,
        }),
      });
      pending.current = null;
      onRun(job);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!rasters.length) return <p>本步需要已加入研究的栅格资料。</p>;
  return (
    <section
      aria-label={operator === "align_grid" ? "空间统一操作" : "波段指标生产"}
    >
      <h3>{operator === "align_grid" ? "参考空间" : "波段指数"}</h3>
      <fieldset className="task-controls" disabled={busy}>
        <label>
          处理资料
          <select
            value={source?.id ?? ""}
            onChange={(e) => patch({ asset_id: e.target.value })}
          >
            <option value="">选择资料</option>
            {rasters.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        {operator === "align_grid" ? (
          <>
            <label>
              参考栅格
              <select
                value={String(parameters.reference_asset_id ?? "")}
                onChange={(e) => patch({ reference_asset_id: e.target.value })}
              >
                <option value="">选择参考网格</option>
                {rasters.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              数值含义
              <select
                value={String(settings.quantity_kind ?? "")}
                onChange={(e) =>
                  patch({
                    quantity_kind: e.target.value,
                    ...(e.target.value === "category"
                      ? { resampling: "nearest" }
                      : {}),
                  })
                }
              >
                <option value="">选择数值类型</option>
                <option value="category">类别编码</option>
                <option value="continuous">连续观测值</option>
              </select>
            </label>
            <label>
              重采样方法
              <select
                value={String(settings.resampling ?? "")}
                onChange={(e) => patch({ resampling: e.target.value })}
              >
                <option value="">选择方法</option>
                <option value="nearest">最近邻</option>
                <option
                  value="bilinear"
                  disabled={settings.quantity_kind === "category"}
                >
                  双线性
                </option>
              </select>
            </label>
            {source && reference ? (
              <details open>
                <summary>网格差异</summary>
                <table aria-label="网格差异">
                  <thead>
                    <tr>
                      <th>项目</th>
                      <th>输入</th>
                      <th>参考</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(["crs", "width", "height", "transform"] as const).map(
                      (key) => (
                        <tr key={key}>
                          <th>
                            {
                              {
                                crs: "坐标系",
                                width: "列数",
                                height: "行数",
                                transform: "网格原点及像元",
                              }[key]
                            }
                          </th>
                          <td>{JSON.stringify(source.facts[key] ?? "未知")}</td>
                          <td>
                            {JSON.stringify(reference.facts[key] ?? "未知")}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </details>
            ) : null}
            <p>总量和密度需要守恒或面积换算，不适用这里的连续值插值。</p>
          </>
        ) : (
          <>
            <p>NDVI =（近红外−红光）/（近红外＋红光）</p>
            {(["red_band", "nir_band"] as const).map((key) => (
              <label key={key}>
                {key === "red_band" ? "红光波段" : "近红外波段"}
                <select
                  value={String(settings[key] ?? "")}
                  onChange={(e) => patch({ [key]: Number(e.target.value) })}
                >
                  <option value="">选择波段</option>
                  {fields.map((field) => (
                    <option key={field.name} value={field.name.slice(5)}>
                      {String(field.description ?? field.name)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
            <label>
              有效观测规则
              <select
                value={String(settings.qa_policy ?? "")}
                onChange={(e) => patch({ qa_policy: e.target.value })}
              >
                <option value="">选择质量规则</option>
                <option value="source_mask">
                  使用文件有效掩膜（不额外判云）
                </option>
              </select>
            </label>
          </>
        )}
        <ErrorNotice error={error} />
        <button
          type="button"
          disabled={!source || busy}
          onClick={() => void run()}
        >
          {busy
            ? "正在提交…"
            : operator === "align_grid"
              ? "生成对齐数据"
              : "计算NDVI指标"}
        </button>
      </fieldset>
    </section>
  );
}
