import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema } from "./api";
import { templateSchema } from "./api";
import { type DraftSession } from "./draft";
import { type Choice } from "./merge";
import { ErrorNotice } from "./shared";
const labels: Record<string, string> = {
  title: "任务名称",
  purpose: "任务目的",
  options: "计算与科学配置",
  mapping: "变量含义与用途",
  selection: "资料与图层选择",
  method_id: "采用方法",
  asset_id: "资料",
  field: "源字段",
  unit: "单位",
  concept: "科学含义",
  support: "观测支撑",
  role: "用途",
  template_id: "依据",
  template_revision: "依据版本",
  revision: "资料版本",
  layer: "图层",
  seed: "随机种子",
  standardize: "标准化",
  definition: "方法定义",
  configuration: "计算规则",
  lower: "参考下限",
  upper: "参考上限",
  positive: "指标方向",
  weight: "权重",
  source_statement: "来源声明",
  observed_year: "声明年份",
  source_description: "资料来源",
  license_statement: "使用限制",
  basis: "依据",
};
function Value({
  value,
  names,
}: {
  value: unknown;
  names: Map<string, string>;
}) {
  if (value === undefined) return <span>未提供</span>;
  if (value === null) return <span>明确为空</span>;
  if (typeof value === "boolean") return <span>{value ? "是" : "否"}</span>;
  if (typeof value === "string" || typeof value === "number")
    return <span>{names.get(String(value)) ?? String(value)}</span>;
  if (Array.isArray(value))
    return (
      <details className="disclosure">
        <summary>{value.length} 项（保留原顺序）</summary>
        <ol>
          {value.map((entry, index) => (
            <li key={index}>
              <Value value={entry} names={names} />
            </li>
          ))}
        </ol>
      </details>
    );
  if (typeof value === "object")
    return (
      <dl className="conflict-values">
        {Object.entries(value).map(([key, entry]) => (
          <div key={key}>
            <dt>{labels[key] ?? key}</dt>
            <dd>
              <Value value={entry} names={names} />
            </dd>
          </div>
        ))}
      </dl>
    );
  return <span>无法显示此值，请保留编辑并重试</span>;
}
export function ConflictPanel({
  session,
  onResolved,
}: {
  session: DraftSession;
  onResolved: () => void;
}) {
  const snapshot = session.snapshot();
  const project = snapshot.task.project_id;
  const assets = useQuery({
    queryKey: ["assets", project],
    enabled: snapshot.conflicts.length > 0,
    queryFn: () => api(`/projects/${project}/assets`, z.array(assetSchema)),
  });
  const templates = useQuery({
    queryKey: ["templates", project],
    enabled: snapshot.conflicts.length > 0,
    queryFn: () =>
      api(`/projects/${project}/templates`, z.array(templateSchema)),
  });
  const [choices, setChoices] = useState<Record<string, Choice>>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  if (!snapshot.conflicts.length) return null;
  const names = new Map([
    ...(assets.data ?? []).map((asset) => [asset.id, asset.name] as const),
    ...(templates.data ?? []).map(
      (template) => [template.id, template.spec.title] as const,
    ),
  ]);
  return (
    <section className="conflict-panel" aria-label="处理并发修改">
      <h2>核对同时发生的修改</h2>
      <p>
        您的编辑仍保留。没有冲突的独立改动自动合并；同一科学配置整组核对，避免把不同单位、阈值或有序数据拼接到一起。
      </p>
      {snapshot.conflicts.map((conflict) => (
        <fieldset key={conflict.path} disabled={busy}>
          <legend>{labels[conflict.path.slice(1)] ?? conflict.path}</legend>
          <div className="form-grid">
            <div>
              <label className="file-choice">
                <input
                  type="radio"
                  name={conflict.path}
                  checked={choices[conflict.path] === "local"}
                  onChange={() =>
                    setChoices((current) => ({
                      ...current,
                      [conflict.path]: "local",
                    }))
                  }
                />
                保留我的修改
              </label>
              <Value value={conflict.local} names={names} />
            </div>
            <div>
              <label className="file-choice">
                <input
                  type="radio"
                  name={conflict.path}
                  checked={choices[conflict.path] === "remote"}
                  onChange={() =>
                    setChoices((current) => ({
                      ...current,
                      [conflict.path]: "remote",
                    }))
                  }
                />
                采用服务器版本
              </label>
              <Value value={conflict.remote} names={names} />
            </div>
          </div>
        </fieldset>
      ))}
      <ErrorNotice error={error ?? assets.error ?? templates.error} />
      <button
        type="button"
        disabled={busy || snapshot.conflicts.some((c) => !choices[c.path])}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            session.resolve(choices);
            await session.save();
            onResolved();
          } catch (e) {
            setError(e);
          } finally {
            setBusy(false);
          }
        }}
      >
        采用选择并继续保存
      </button>
    </section>
  );
}
