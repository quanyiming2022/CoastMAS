import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError } from "./api";
import { ErrorNotice } from "./shared";
const planSchema = z.object({
  method: z.literal("ahp"),
  labels: z.array(z.string()),
  matrix: z.array(z.array(z.number().nullable())),
  consistency_limit: z.number(),
  source: z.unknown().optional(),
});
const reportSchema = z.object({
  indicators: z.array(z.string()),
  weights: z.array(z.number()),
  lambda_max: z.number(),
  consistency_index: z.number().nullable(),
  random_index: z.number(),
  consistency_ratio: z.number().nullable(),
  consistency_applicable: z.boolean(),
  note: z.string(),
});
export type AhpPlan = z.infer<typeof planSchema>;
export const blankAhp = (labels: string[]): AhpPlan => ({
  method: "ahp",
  labels,
  matrix: labels.map((_, i) => labels.map((_, j) => (i === j ? 1 : null))),
  consistency_limit: 0.1,
});
export function AhpMatrix({
  project,
  indicators,
  definition,
  change,
}: {
  project: string;
  indicators: string[];
  definition: unknown;
  change: (plan: AhpPlan) => void;
}) {
  const parsed = planSchema.safeParse(definition),
    plan = parsed.success ? parsed.data : blankAhp(indicators);
  const [file, setFile] = useState<File | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [aliases, setAliases] = useState<Record<string, string>>({}),
    [unmatched, setUnmatched] = useState<string[]>([]);
  const matches =
    indicators.length > 0 &&
    new Set(indicators).size === indicators.length &&
    indicators.every((id) => id && plan.labels.includes(id)) &&
    plan.labels.length === indicators.length;
  const complete =
    matches &&
    plan.matrix.length === indicators.length &&
    plan.matrix.every(
      (row) => row.length === indicators.length && row.every((n) => n !== null),
    );
  const preview = useQuery({
    queryKey: ["ahp-preview", project, plan, indicators],
    enabled: complete,
    queryFn: () =>
      api(`/projects/${project}/ahp/preview`, reportSchema, {
        method: "POST",
        body: JSON.stringify({ definition: plan, indicators }),
      }),
    retry: false,
  });
  function judgment(i: number, j: number, text: string) {
    const value = text === "" ? null : Number(text);
    const matrix = plan.matrix.map((row) => [...row]);
    matrix[i]![j] = value;
    matrix[j]![i] =
      value !== null && Number.isFinite(value) && value > 0 ? 1 / value : null;
    change({ ...plan, matrix });
  }
  async function imported() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.set("file", file);
      body.set("indicators", JSON.stringify(indicators));
      body.set("consistency_limit", String(plan.consistency_limit));
      body.set("aliases", JSON.stringify(aliases));
      const next = await api(
        `/projects/${project}/ahp/import`,
        z.object({ definition: planSchema, report: reportSchema }),
        { method: "POST", body },
      );
      change(next.definition);
      setUnmatched([]);
    } catch (failure) {
      setError(failure);
      if (failure instanceof APIError && failure.code === "AHP_IDENTITIES") {
        const data = z
          .object({ matrix: z.array(z.string()) })
          .safeParse(failure.details);
        if (data.success) setUnmatched(data.data.matrix);
      }
    } finally {
      setBusy(false);
    }
  }
  const errorDetails =
    preview.error instanceof APIError ? preview.error.details : null;
  const failedReport = reportSchema.safeParse(errorDetails),
    report = preview.data ?? (failedReport.success ? failedReport.data : null);
  return (
    <section className="ahp-editor" aria-label="AHP判断矩阵">
      <div className="section-heading">
        <h3>成对判断矩阵</h3>
        <span>主特征向量 · Saaty 1—10阶RI档案</span>
      </div>
      {!matches ? (
        <div role="alert">
          <p>矩阵与当前指标集合不一致，保留原判断，先核对指标名称。</p>
          <button
            type="button"
            className="secondary"
            disabled={!indicators.length || indicators.some((id) => !id)}
            onClick={() => {
              if (
                window.confirm(
                  "按当前指标重建空矩阵？此草稿原有判断将被替换，已发布版本保留。",
                )
              )
                change(blankAhp(indicators));
            }}
          >
            按当前指标重建空矩阵
          </button>
        </div>
      ) : null}
      <div className="table-scroll">
        <table className="ahp-matrix">
          <thead>
            <tr>
              <th>行相对列的重要程度</th>
              {plan.labels.map((label, i) => (
                <th key={i}>{label || "待命名"}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {plan.labels.map((label, i) => (
              <tr key={i}>
                <th>{label || "待命名"}</th>
                {plan.labels.map((other, j) => (
                  <td key={j}>
                    <input
                      type="number"
                      step="any"
                      min={1 / 9}
                      max={9}
                      aria-label={`${label}相对${other}`}
                      value={plan.matrix[i]?.[j] ?? ""}
                      readOnly={i >= j}
                      onChange={(e) => judgment(i, j, e.target.value)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        填写上三角判断，对角与倒数按定义自动处理。导入的矛盾值不会自动修正；发布前必须通过结构与适用一致性检查。
      </p>
      <label>
        一致性比率阈值
        <input
          aria-label="AHP一致性阈值"
          type="number"
          min="0.001"
          max="0.1"
          step="0.01"
          value={plan.consistency_limit}
          onChange={(e) =>
            change({ ...plan, consistency_limit: Number(e.target.value) })
          }
        />
      </label>
      {preview.isFetching ? <p role="status">正在计算权重与一致性…</p> : null}
      <ErrorNotice error={error ?? preview.error} />
      {report ? (
        <>
          <p role="status">
            {report.consistency_applicable
              ? `λmax ${report.lambda_max.toPrecision(6)} · CI ${report.consistency_index?.toPrecision(4)} · RI ${report.random_index} · CR ${report.consistency_ratio?.toPrecision(4)}`
              : report.note}
          </p>
          <dl className="ahp-weights">
            {report.indicators.map((label, i) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{report.weights[i]?.toPrecision(6)}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}
      <details>
        <summary>导入已有CSV/XLSX矩阵</summary>
        <label>
          判断矩阵文件
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
              setAliases({});
              setUnmatched([]);
            }}
          />
        </label>
        {unmatched.map((label) => (
          <label key={label}>
            {label}对应指标
            <select
              value={aliases[label] ?? ""}
              onChange={(e) =>
                setAliases({ ...aliases, [label]: e.target.value })
              }
            >
              <option value="">选择科学含义</option>
              {indicators.map((id) => (
                <option key={id}>{id}</option>
              ))}
            </select>
          </label>
        ))}
        <button
          type="button"
          className="secondary"
          disabled={!file || busy || indicators.some((id) => !id)}
          onClick={() => void imported()}
        >
          读取并匹配判断矩阵
        </button>
      </details>
    </section>
  );
}
