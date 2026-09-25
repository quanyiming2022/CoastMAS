import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, jobSchema, type Asset } from "./api";
import type { TaskRecord, Draft } from "./draft";
import { ErrorNotice } from "./shared";
import { record } from "./ResearchStepPanel";

const unitVersion = z.object({
  id: z.string(),
  job_id: z.string(),
  version: z.number(),
  unit_count: z.number(),
  geometry_type: z.string(),
  applicable: z.boolean(),
  algorithm_version: z.string(),
});
export function PlanningUnitPreparation({
  task,
  assets,
  edit,
  save,
  onRun,
}: {
  task: TaskRecord;
  assets: Asset[];
  edit: (f: (d: Draft) => Draft) => void;
  save: () => Promise<TaskRecord>;
  onRun: (job: z.infer<typeof jobSchema>) => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const intent = useRef<{ fingerprint: string; key: string } | null>(null);
  const candidates = assets.filter((a) =>
    ["geojson", "geopackage", "shapefile", "csv", "csvw"].includes(
      a.facts.profile,
    ),
  );
  const settings = record(task.draft.options.planning_preparation);
  const source =
    candidates.find((a) => a.id === settings.asset_id) ??
    (candidates.length === 1 ? candidates[0] : undefined);
  const versions = useQuery({
    queryKey: ["planning-units", task.id, task.revision],
    queryFn: () =>
      api(`/v1/tasks/${task.id}/planning/units`, z.array(unitVersion)),
    refetchInterval: busy ? 1000 : 5000,
  });
  async function run() {
    if (!source) return;
    setBusy(true);
    setError(null);
    try {
      const current = await save();
      const fingerprint = JSON.stringify([current.revision, source.id]);
      if (intent.current?.fingerprint !== fingerprint)
        intent.current = { fingerprint, key: crypto.randomUUID() };
      const key = intent.current.key;
      const node = await api(
        `/tasks/${current.id}/processing-nodes`,
        z.object({ id: z.string() }),
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: current.revision,
            asset_id: source.id,
            operator: "planning_units",
            parameters: {},
            idempotency_key: key,
          }),
        },
      );
      const job = await api(`/processing-nodes/${node.id}/execute`, jobSchema, {
        method: "POST",
        body: JSON.stringify({
          expected_revision: current.revision,
          idempotency_key: key,
        }),
      });
      onRun(job);
      await versions.refetch();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="规划单元准备" className="planning-unit-preparation">
      <h3>规划单元</h3>
      {!candidates.length ? (
        <p>添加已有分区矢量或设施候选点。栅格划分服务尚未接通。</p>
      ) : (
        <>
          {candidates.length === 1 ? (
            <p title={source?.name}>{source?.name}</p>
          ) : (
            <label>
              单元来源
              <select
                value={source?.id ?? ""}
                onChange={(e) =>
                  edit((d) => ({
                    ...d,
                    options: {
                      ...d.options,
                      planning_preparation: { asset_id: e.target.value },
                    },
                  }))
                }
              >
                <option value="">选择分区或候选点</option>
                {candidates.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            disabled={busy || !source}
            onClick={() => void run()}
          >
            {busy ? "正在提交…" : "生成规划单元"}
          </button>
          <details>
            <summary>处理范围</summary>
            <p>
              保留全部要素和原始字段；面单元计算面积并检查重叠，点单元不推测面积。此步骤不求解方案，也不猜成本、收益或时期。
            </p>
          </details>
        </>
      )}
      <ErrorNotice error={error ?? versions.error} />
      {versions.data?.length ? (
        <ul className="step-inputs">
          {versions.data.map((v) => (
            <li key={v.id}>
              <span>
                v{v.version} · {v.unit_count}个
                {v.geometry_type === "point" ? "候选点" : "面单元"} ·{" "}
                {v.applicable ? "来源仍适用" : "输入已变化"}
              </span>
              <button
                type="button"
                className="text-button"
                onClick={() =>
                  void api(`/jobs/${v.job_id}`, jobSchema)
                    .then(onRun)
                    .catch(setError)
                }
              >
                查看产物
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
