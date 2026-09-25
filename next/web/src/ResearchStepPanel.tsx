import { useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, templateSchema, type Asset } from "./api";
import { draftSchema, type TaskRecord } from "./draft";
import { type ResearchStep } from "./ResearchPanels";
import {
  ConfigurationIssues,
  type ConfigurationReview,
  type ConfigurationIssue,
} from "./ConfigurationReview";
import { ErrorNotice } from "./shared";
export const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
export const values = (value: unknown): unknown[] =>
  Array.isArray(value) ? value : [];
const display = (value: unknown) =>
  value === null || value === undefined
    ? "未提供"
    : typeof value === "boolean"
      ? value
        ? "是"
        : "否"
      : String(value);
export function stepStatus(
  step: ResearchStep,
  scope: "draft" | "run",
  task: TaskRecord,
  job?: Record<string, unknown>,
  data?: Record<string, unknown>,
) {
  if (!["sources", "spatial", "indicators", "weights", "synthesis", "validation", "normalization", "spatialization", "objectives", "constraints"].includes(step))
    return {label:"未接通",note:"此阶段业务服务尚未实现，不会使用其他算法代替。"};
  const planningKind = step === "objectives" ? "objectives" : step === "constraints" ? "constraints" : null;
  if (task.draft.options.task_type === "planning" && planningKind) {
    const refs = record(scope === "run" ? record(record(record(job?.manifest).draft).options).planning_refs : task.draft.options.planning_refs);
    const complete = planningKind === "constraints" ? !!refs.constraints && !!refs.decisions : !!refs.objectives;
    return {label: complete ? "已引用" : "待配置", note: "固定配置引用，不代表诊断、求解或业务验证已通过。"};
  }
  const manifest = record(job?.manifest);
  const matching = scope === "run" || manifest.draft_revision === task.revision;
  const sourceCount =
    scope === "run"
      ? values(manifest.assets).length
      : task.draft.selection.length;
  if (step === "sources")
    return {
      label: sourceCount ? "已引用" : "待补",
      note: sourceCount
        ? "已登记的输入引用；不等于全部科学预检通过。"
        : "尚未选择本研究要使用的资料。",
    };
  if (step === "synthesis" && matching && job && !manifest.processing_node_id && ["assessment", "optimization"].includes(String(record(manifest.draft).purpose))) {
    const states: Record<string, string> = {
      queued: "排队",
      running: "运行中",
      failed: "失败",
      cancelled: "已取消",
      succeeded: "已运行",
    };
    return {
      label: states[String(job.status)] ?? "待核查",
      note: "仅反映所示运行的实际执行状态，不代表独立科学验证通过。",
    };
  }
  if (step === "validation")
    return {
      label:
        data?.business_validated === true && matching ? "已验证" : "待验证",
      note: "工程执行成功不替代独立精度、适用性和科学依据核验。",
    };
  if (
    scope === "run" &&
    job?.status === "succeeded" &&
    ["normalization", "weights"].includes(step)
  ) {
    const role = step === "normalization" ? "indicator" : "contribution";
    if (values(data?.files).some((file) => record(file).role === role))
      return { label: "有产物", note: "此固定运行保存了对应实际产物。" };
  }
  return {
    label: "待核查",
    note: "只展示真实配置和证据；查看、保存或运行其他步骤不会把此项标成完成。",
  };
}
export function ResearchStepPanel({
  step,
  scope,
  task,
  assets,
  job,
  result,
  onScope,
  onAdd,
  onInspect,
  onRepair,
  review,
}: {
  step: ResearchStep;
  scope: "draft" | "run";
  task: TaskRecord;
  assets: Asset[];
  job?: Record<string, unknown>;
  result?: Record<string, unknown>;
  onScope: (scope: "draft" | "run") => void;
  onAdd?: () => void;
  onInspect?: (id: string) => void;
  onRepair?: (issue: ConfigurationIssue) => void;
  review?: ConfigurationReview;
}) {
  const scopeId = useId();
  const manifest = record(job?.manifest);
  const frozen = draftSchema.safeParse(manifest.draft);
  const draft =
    scope === "run" ? (frozen.success ? frozen.data : null) : task.draft;
  const fixedMethod = useQuery({
    queryKey: [
      "method-version",
      draft?.method_id,
      draft?.options.method_revision,
    ],
    queryFn: () =>
      api(
        `/methods/${draft?.method_id}/versions/${String(draft?.options.method_revision)}`,
        templateSchema,
      ),
    enabled: scope === "draft" && !!draft?.method_id,
  });
  const method = scope === "run" ? record(manifest.method) : fixedMethod.data;
  const spec = record(record(method).spec),
    configuration = record(spec.configuration),
    indicators = values(configuration.indicators).map(record);
  const inputs = scope === "run" ? values(manifest.assets).map(record) : assets;
  const hasSpatial =
    inputs.some((a) =>
      ["geotiff", "cog", "geojson", "gpkg", "geopackage", "shapefile"].includes(
        String(record(a.facts).profile),
      ),
    ) || !!draft?.options.spatial_reference;
  const roles: Partial<Record<ResearchStep, string[]>> = {
    indicators: ["raw_indicator"],
    normalization: ["indicator"],
    weights: ["contribution"],
    synthesis: ["composite"],
    validation: ["quality"],
  };
  const files = values(result?.files)
    .map((f, index): Record<string, unknown> & { index: number } => ({
      ...record(f),
      index,
    }))
    .filter((f) => roles[step]?.includes(String(f.role)));
  const methodNames: Record<string, string> = {
    weighted: "加权综合",
    entropy: "熵权综合",
    topsis: "TOPSIS排序",
    binary_allocation: "约束优化",
  };
  if (task.draft.options.task_type === "planning" && ["objectives", "constraints"].includes(step)) {
    if (scope === "draft") return null;
    const refs = record(draft?.options.planning_refs);
    const kinds = step === "objectives" ? ["objectives"] : ["constraints", "decisions"];
    return <section aria-label="固定运行规划配置">{kinds.map(kind => {const ref=record(refs[kind]);return <p key={kind}>{kind === "objectives" ? "规划目标" : kind === "constraints" ? "约束" : "决策变量"}：{ref.version ? `固定版本 v${String(ref.version)}` : "此运行未引用"}</p>;})}</section>;
  }
  if (scope === "draft" && step === "sources" && !task.draft.selection.length)
    return (
      <section className="research-step-summary">
        <p>尚未添加输入资料</p>
        <button type="button" onClick={onAdd} disabled={!onAdd}>
          添加资料
        </button>
      </section>
    );
  if (!["sources", "spatial", "indicators", "weights", "synthesis", "validation", "normalization", "spatialization"].includes(step))
    return <section className="research-step-summary" aria-label="步骤实现状态"><p>此阶段的业务服务尚未接通。当前资料、草稿与历史成果保留；不会自动执行其他算法代替。</p></section>;
  return (
    <section className="research-step-summary" aria-label="步骤配置与依据">
      {job && frozen.success ? (
        <label htmlFor={scopeId}>
          查看配置
          <select
            id={scopeId}
            value={scope}
            onChange={(e) => onScope(e.target.value as "draft" | "run")}
          >
            <option value="draft">当前配置</option>
            <option value="run">本次运行使用的配置（只读）</option>
          </select>
        </label>
      ) : null}
      {scope === "run" ? (
        <p className="step-version">
          运行 #{String(job?.id).slice(0, 8)} · 配置 v
          {String(manifest.draft_revision)}
        </p>
      ) : null}
      <ErrorNotice error={fixedMethod.error} />
      {!draft ? (
        <p role="alert">无法读取本次运行的配置，请重新打开运行详情。</p>
      ) : (
        <>
          {step === "sources" ? (
            <>
              <div className="section-heading">
                <h3>输入资料</h3>
                {scope === "draft" ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={onAdd}
                    disabled={!onAdd}
                  >
                    添加资料
                  </button>
                ) : null}
              </div>
              <ul className="step-inputs">
                {inputs.map((a, i) => (
                  <li key={String(a.id ?? i)}>
                    {scope === "draft" ? (
                      <button
                        type="button"
                        className="text-button"
                        title={String(a.name)}
                        onClick={() => onInspect?.(String(a.id))}
                      >
                        {String(a.name)}
                      </button>
                    ) : (
                      <span>{String(a.name)}</span>
                    )}
                    <span>{String(record(a.facts).profile ?? "类型未知")}</span>
                    <details>
                      <summary>来源详情</summary>
                      <p>版本 {String(a.revision ?? "未知")}</p>
                      <p>
                        SHA256 <code>{String(a.sha256 ?? "未提供")}</code>
                      </p>
                    </details>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          {step === "spatial" ? (
            <>
              {hasSpatial ? (
                <>
                  <h3>输入定位</h3>
                  <ul>
                    {inputs.map((a, i) => (
                      <li key={String(a.id ?? i)}>
                        {String(a.name)} ·{" "}
                        {String(record(a.facts).crs ?? "坐标系待核对")}
                      </li>
                    ))}
                  </ul>
                  <p>当前使用输入原生网格。</p>
                </>
              ) : (
                <p>当前资料未关联空间位置，可继续数值计算。</p>
              )}
            </>
          ) : null}
          {step === "spatialization" ? (
            <p>
              {draft.options.spatialization
                ? "统计空间化处理尚未接入，当前配置不能执行此步骤。"
                : "尚未确定是否需要统计空间化；须依据指标来源与所选处理路线判断。"}
            </p>
          ) : null}
          {step === "indicators" && scope === "run" ? (
            <>
              <h3>本次指标</h3>
              <ul>
                {draft.mapping
                  .filter((m) => ["feature", "response"].includes(m.role))
                  .map((m, i) => (
                    <li key={i}>
                      {m.concept ?? m.field} · {m.unit ?? "单位未确认"}
                      <details>
                        <summary>来源字段</summary>
                        {m.field}
                      </details>
                    </li>
                  ))}
              </ul>
            </>
          ) : null}
          {step === "indicators" &&
          scope === "draft" &&
          !draft.mapping.length ? (
            <p>添加资料后可选择指标字段。</p>
          ) : null}
          {["normalization", "weights", "synthesis"].includes(step) &&
          method ? (
            <>
              <h3>
                {step === "weights"
                  ? "权重方法"
                  : step === "normalization"
                    ? "评分规则"
                    : "综合方法"}
              </h3>
              <p>
                {String(spec.title)} · 第{String(record(method).revision)}版
              </p>
              <p>
                {configuration.weighting
                  ? "AHP判断赋权"
                  : (methodNames[String(configuration.method)] ??
                    String(configuration.method ?? "尚未选择"))}
              </p>
              <ul>
                {indicators.map((i, index) => (
                  <li key={index}>
                    {String(i.concept)}
                    {step === "weights"
                      ? ` · 权重 ${display(i.weight)}`
                      : step === "normalization"
                        ? ` · ${display(i.lower)}—${display(i.upper)} ${display(i.unit)} · ${i.positive === true ? "正向" : i.positive === false ? "负向" : "方向未设置"}`
                        : ""}
                  </li>
                ))}
              </ul>
              <details>
                <summary>方法依据</summary>
                {String(spec.basis ?? "未提供")}
              </details>
            </>
          ) : null}
          {step === "validation" ? (
            <>
              {job ? (
                <>
                  <p>
                    {job.status === "succeeded"
                      ? "计算已完成，可查看成果与检查记录。"
                      : job.status === "failed"
                        ? "计算失败，请查看运行错误。"
                        : "当前运行尚未完成。"}
                  </p>
                  {job.error ? (
                    <ErrorNotice
                      error={new Error(String(record(job.error).message))}
                    />
                  ) : null}
                  <details>
                    <summary>业务验证依据</summary>
                    {result?.business_validated === true
                      ? "本次记录已通过业务验证。"
                      : "尚无独立业务验证依据；计算完成不代表业务验证通过。"}
                  </details>
                </>
              ) : (
                <p>完成计算后可检查和导出成果。</p>
              )}
            </>
          ) : null}
          {scope === "draft" && review && onRepair ? (
            <ConfigurationIssues
              review={review}
              step={step}
              onAction={onRepair}
            />
          ) : null}
          {files.length && job ? (
            <details>
              <summary>本步处理结果 · {files.length}项</summary>
              <ul>
                {files.map((f) => (
                  <li key={f.index}>
                    <a href={`/api/jobs/${job.id}/files/${f.index}`} download>
                      {String(f.title ?? f.name)}
                    </a>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      )}
    </section>
  );
}
