import { useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { z } from "zod";
import { request, resourceSchema } from "./api";
import { contract } from "./contracts";
import { ErrorNotice, PageTitle, Panel } from "./components";
import { useWorkspace } from "./workspace";
import type { TemporalRequest } from "./generated/contracts";
import {
  allowedMethods,
  temporalMethods,
  observationValue,
} from "./temporal-editor";

const reference = z.object({ id: z.string(), version: z.number().int() });
const prepared = z.object({
  data: reference,
  scene: reference,
  workflow: reference,
});
const emptyObservation = () => ({ start: "", end: "", value: "" });
export default function TemporalAdaptation() {
  const { projectId } = useWorkspace();
  return <TemporalForm key={projectId} projectId={projectId} />;
}
function TemporalForm({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [fields, setFields] = useState({
    name: "",
    source: "",
    license: "",
    variable: "",
    unit: "",
    outputUnit: "",
    start: "",
    end: "",
  });
  const [sceneId, setSceneId] = useState("");
  const [aggregation, setAggregation] =
    useState<TemporalRequest["aggregation_type"]>("intensive");
  const [method, setMethod] = useState<TemporalRequest["method"]>("mean");
  const [support, setSupport] =
    useState<TemporalRequest["support"]>("interval");
  const [policy, setPolicy] = useState<"propagate" | "reject">("propagate");
  const [observations, setObservations] = useState([emptyObservation()]);
  const key = useRef({ signature: "", key: "" });
  const pointTarget = method === "nearest" || method === "interpolation";
  const actualSupport =
    pointTarget ||
    aggregation === "instantaneous" ||
    aggregation === "categorical"
      ? "point"
      : method === "mean" || method === "sum"
        ? "interval"
        : support;
  const catalog = useQuery({
    queryKey: ["temporal-scenes", projectId],
    queryFn: ({ signal }) =>
      request(
        `/scenes?project_id=${encodeURIComponent(projectId)}&limit=500`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const save = useMutation({
    mutationFn: () => {
      const selected = catalog.data?.find((row) => row.id === sceneId);
      if (!selected) throw new Error("请选择沿用研究区的场景。");
      const frame = contract("TemporalRequest").parse({
        variable: fields.variable,
        unit: fields.unit,
        output_unit: fields.outputUnit,
        aggregation_type: aggregation,
        support: actualSupport,
        method,
        nodata_policy: policy,
        ...(pointTarget
          ? { target_time: fields.start }
          : { window_start: fields.start, window_end: fields.end }),
        observations: observations.map((row) => ({
          start: row.start,
          end: actualSupport === "point" ? row.start : row.end,
          value: observationValue(row.value),
        })),
      });
      const body = {
        project_id: projectId,
        name: fields.name,
        source: fields.source,
        license: fields.license,
        scene: { id: sceneId, version: selected.version },
        request: frame,
      };
      const signature = JSON.stringify(body);
      if (key.current.signature !== signature)
        key.current = { signature, key: crypto.randomUUID() };
      return request("/adaptations/temporal", prepared, {
        method: "POST",
        body: contract("SaveTemporalRequest").parse({
          ...body,
          idempotency_key: key.current.key,
        }),
      });
    },
    onSuccess: (record) =>
      navigate(
        `/workflows/${encodeURIComponent(record.workflow.id)}?scene=${encodeURIComponent(record.scene.id)}`,
      ),
  });
  return (
    <>
      <PageTitle
        title="时间适配"
        description="依据实际观测支撑转换时间尺度，保留单位、缺测策略和固定版本。"
      />
      <ErrorNotice error={catalog.error ?? save.error} />
      <fieldset disabled={save.isPending}>
        <Panel title="来源与科学含义">
          <label>
            沿用研究区的场景
            <select
              value={sceneId}
              onChange={(event) => setSceneId(event.target.value)}
            >
              <option value="">请选择场景</option>
              {catalog.data?.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} · v{row.version}
                </option>
              ))}
            </select>
          </label>
          <p>
            保存时创建独立场景版本，沿用研究区并采用下方目标时间；原场景保留。
          </p>
          <div className="form-grid">
            {(
              [
                ["name", "名称"],
                ["source", "数据来源"],
                ["license", "许可证"],
                ["variable", "物理变量"],
                ["unit", "输入单位"],
                ["outputUnit", "输出单位"],
              ] as const
            ).map(([name, label]) => (
              <label key={name}>
                {label}
                <input
                  value={fields[name]}
                  onChange={(event) =>
                    setFields({ ...fields, [name]: event.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <label>
            统计含义
            <select
              value={aggregation}
              onChange={(event) => {
                const next = event.target
                  .value as TemporalRequest["aggregation_type"];
                setAggregation(next);
                setMethod(allowedMethods[next][0]!);
              }}
            >
              <option value="intensive">连续量 / 区间平均</option>
              <option value="extensive">总量 / 区间累计</option>
              <option value="instantaneous">瞬时量</option>
              <option value="categorical">类别</option>
            </select>
          </label>
          <label>
            适配方法
            <select
              value={method}
              onChange={(event) =>
                setMethod(event.target.value as TemporalRequest["method"])
              }
            >
              {allowedMethods[aggregation].map((option) => (
                <option key={option} value={option}>
                  {temporalMethods[option]}
                </option>
              ))}
            </select>
          </label>
          {(method === "min" || method === "max") &&
          aggregation === "intensive" ? (
            <label>
              观测支撑
              <select
                value={support}
                onChange={(event) =>
                  setSupport(event.target.value as TemporalRequest["support"])
                }
              >
                <option value="interval">实际区间</option>
                <option value="point">观测时刻</option>
              </select>
            </label>
          ) : (
            <p>
              观测支撑：{actualSupport === "point" ? "观测时刻" : "实际区间"}
            </p>
          )}
          <label>
            缺测策略
            <select
              value={policy}
              onChange={(event) =>
                setPolicy(event.target.value as "propagate" | "reject")
              }
            >
              <option value="propagate">传播缺测，结果保持未知</option>
              <option value="reject">拒绝含缺测的计算</option>
            </select>
          </label>
        </Panel>
        <Panel title="目标时间与观测">
          <p>
            时间必须带时区，如
            2025-01-01T00:00:00Z。按时间排序；数值留空表示缺测。区间平均按实际时长加权，累计值每段只加一次；禁止外推、区间重叠和聚合空档。
          </p>
          <label>
            {pointTarget ? "目标时刻" : "目标开始时间"}
            <input
              value={fields.start}
              onChange={(event) =>
                setFields({ ...fields, start: event.target.value })
              }
            />
          </label>
          {!pointTarget ? (
            <label>
              目标结束时间
              <input
                value={fields.end}
                onChange={(event) =>
                  setFields({ ...fields, end: event.target.value })
                }
              />
            </label>
          ) : null}
          <div className="table-scroll">
            <table aria-label="时间观测">
              <thead>
                <tr>
                  <th>{actualSupport === "point" ? "观测时刻" : "区间开始"}</th>
                  {actualSupport === "interval" ? <th>区间结束</th> : null}
                  <th>数值</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {observations.map((row, index) => (
                  <tr key={index}>
                    {(
                      [
                        "start",
                        ...(actualSupport === "interval"
                          ? ["end" as const]
                          : []),
                        "value",
                      ] as const
                    ).map((field) => (
                      <td key={field}>
                        <input
                          aria-label={`观测${index + 1}${field === "start" ? "开始" : field === "end" ? "结束" : "数值"}`}
                          value={row[field]}
                          onChange={(event) =>
                            setObservations(
                              observations.map((item, at) =>
                                at === index
                                  ? { ...item, [field]: event.target.value }
                                  : item,
                              ),
                            )
                          }
                        />
                      </td>
                    ))}
                    <td>
                      <button
                        className="secondary"
                        disabled={observations.length === 1}
                        onClick={() =>
                          setObservations(
                            observations.filter((_, at) => at !== index),
                          )
                        }
                      >
                        删除观测{index + 1}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            className="secondary"
            disabled={observations.length >= 10000}
            onClick={() =>
              setObservations([...observations, emptyObservation()])
            }
          >
            添加观测
          </button>
          <p>
            极值只描述观测值，不代表未观测时段的连续极值。保存不会调用 LLM。
          </p>
          <button
            disabled={!sceneId || save.isPending}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "保存中…" : "保存时间适配工作流"}
          </button>
        </Panel>
      </fieldset>
    </>
  );
}
