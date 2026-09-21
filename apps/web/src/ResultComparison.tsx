import { DataTable } from "./components";
import { useQueries } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { request } from "./api";
import { payloadSchema } from "./result-payload";
import {
  comparisonRows,
  type ComparedValue,
  type ComparisonRow,
} from "./result-comparison";
import { useWorkspace } from "./workspace";
import {
  Details,
  display,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
} from "./components";
import { ResultValue } from "./Results";

export default function ResultComparison() {
  const [parameters] = useSearchParams();
  const { projectId } = useWorkspace();
  const ids = [parameters.get("left") ?? "", parameters.get("right") ?? ""];
  const queries = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["comparison-content", projectId, id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        request(`/results/${encodeURIComponent(id)}/content`, payloadSchema, {
          signal,
        }),
      enabled: ids.every(Boolean),
      retry: false,
    })),
  });
  const left = queries[0]?.data,
    right = queries[1]?.data;
  let rows: ComparisonRow[] = [];
  let comparisonError: unknown;
  try {
    if (left?.result_view && right?.result_view)
      rows = comparisonRows(left.result_view, right.result_view);
  } catch (error) {
    comparisonError = error;
  }
  return (
    <>
      <Link to="/results">← 返回结果中心</Link>
      <PageTitle
        title="场景结果比较"
        description="并列查看两份不可变运行结果、指标单位和完整来源。"
      />
      {!ids.every(Boolean) ? <p>请在结果中心选择两份结果。</p> : null}
      {ids.every(Boolean) && queries.some((query) => query.isPending) ? (
        <Loading />
      ) : null}
      {queries.map((query, index) => (
        <ErrorNotice key={index} error={query.error} />
      ))}
      <ErrorNotice error={comparisonError} />
      {left && right ? (
        <>
          <div className="result-comparison-grid">
            {[left, right].map((result, index) => (
              <Panel key={index} title={index === 0 ? "左侧结果" : "右侧结果"}>
                <Link
                  className="break"
                  to={`/results/${encodeURIComponent(ids[index]!)}`}
                >
                  {ids[index]}
                </Link>
                <dl className="definition-grid">
                  <div>
                    <dt>场景</dt>
                    <dd>
                      {result.run_manifest.scene.name} · v
                      {result.run_manifest.scene.version}
                    </dd>
                  </div>
                  <div>
                    <dt>工作流</dt>
                    <dd>
                      {result.run_manifest.workflow.name} · v
                      {result.run_manifest.workflow.version}
                    </dd>
                  </div>
                  <div>
                    <dt>时间范围</dt>
                    <dd>
                      {result.run_manifest.scene.time_range.start} —{" "}
                      {result.run_manifest.scene.time_range.end}
                    </dd>
                  </div>
                </dl>
                <Details
                  title="范围、参数与数据来源"
                  value={{
                    scene: result.run_manifest.scene,
                    models: result.run_manifest.models.map((model) => ({
                      id: model.id,
                      version: model.version,
                    })),
                    nodes: result.run_manifest.workflow.nodes,
                    inputs: result.run_manifest.data_assets.map((asset) => ({
                      id: asset.id,
                      version: asset.version,
                      checksum: asset.checksum,
                    })),
                    input_fingerprint: result.input_fingerprint,
                  }}
                />
                <a
                  className="button secondary"
                  href={`/api/v1/results/${encodeURIComponent(ids[index]!)}/content`}
                  download={`coastmas-${ids[index]}.json`}
                >
                  下载{index === 0 ? "左侧" : "右侧"}完整结果
                </a>
              </Panel>
            ))}
          </div>
          <Panel title="管理指标对照">
            <p>
              按节点、输出、科学变量和管理单元标识对齐，保留原始值与单位。缺项保持缺项；同名管理单元仍需核对两次运行的实体版本和范围。
            </p>
            <p>
              不同模型、参考框架或数据范围可能导致不可比；本页提供原值并列对照，科学变化指标以相应模型的验证输出为准。
            </p>
            {rows.length ? (
              <DataTable aria-label="管理指标对照表">
                <thead>
                  <tr>
                    <th>来源 / 管理单元 / 指标</th>
                    <th className="numeric">左侧原值</th>
                    <th className="numeric">右侧原值</th>
                    <th>单位核对</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id}>
                      <td>
                        {row.nodeId} / {row.variable}
                        <br />
                        {row.managementUnit ?? "无管理标识"} / {row.metric}
                        <small className="break">{row.standardName}</small>
                      </td>
                      <td className="numeric">
                        <Value value={row.left} />
                      </td>
                      <td className="numeric">
                        <Value value={row.right} />
                      </td>
                      <td>
                        {!row.left || !row.right
                          ? "单侧缺项"
                          : row.sameUnit
                            ? "单位相同"
                            : "单位不同或未声明"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            ) : (
              <p>没有可对齐的结构化管理指标；下方保留两侧原始输出。</p>
            )}
          </Panel>
          <div className="result-comparison-grid">
            {[left, right].map((result, index) => (
              <section
                aria-label={index === 0 ? "左侧原始输出" : "右侧原始输出"}
                key={index}
              >
                {Object.entries(result.outputs).map(([name, value]) => (
                  <Panel
                    key={name}
                    title={`${index === 0 ? "左" : "右"} · ${name}`}
                  >
                    <ResultValue value={value} />
                  </Panel>
                ))}
              </section>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}
function Value({ value }: { value: ComparedValue | null }) {
  if (!value) return <>缺项</>;
  return (
    <>
      <span>
        {display(value.value)} {value.unit ?? "单位未声明"}
      </span>
      <small className="break">
        {value.model.id} · v{value.model.version}
      </small>
    </>
  );
}
