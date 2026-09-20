import { lazy, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import { request, resultSchema } from "./api";
import { contract } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  Details,
  display,
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
} from "./components";
import { geographicCollection, coastalStatistics } from "./result-data";
const GeoMap = lazy(() => import("./GeoMap"));
const CoastalStatistics = lazy(() => import("./CoastalStatistics"));
const payloadSchema = z.object({
  outputs: z.record(z.string(), z.unknown()),
  node_outputs: z.record(z.string(), z.unknown()),
  executed_nodes: z.array(z.string()),
  elapsed_seconds: z.number().nonnegative(),
  llm_calls: z.number().int().nonnegative(),
  run_manifest: contract("RunManifest"),
  input_fingerprint: z.string(),
});
export default function Results() {
  const { projectId } = useWorkspace();
  const query = useQuery({
    queryKey: ["results", projectId],
    queryFn: ({ signal }) =>
      request(
        "/results?project_id=" + encodeURIComponent(projectId),
        z.array(resultSchema),
        { signal },
      ),
  });
  return (
    <>
      <PageTitle
        title="结果中心"
        description="每份结果保留独立版本、输入指纹和完整计算来源。"
      />
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      <Panel title="结果版本">
        {query.data?.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>结果</th>
                  <th>任务</th>
                  <th>生成时间</th>
                </tr>
              </thead>
              <tbody>
                {query.data.map((result) => (
                  <tr key={result.id}>
                    <td>
                      <Link to={"/results/" + encodeURIComponent(result.id)}>
                        {result.id.slice(0, 12)}
                      </Link>
                    </td>
                    <td>
                      <Link to={"/runs/" + encodeURIComponent(result.job_id)}>
                        {result.job_id.slice(0, 12)}
                      </Link>
                    </td>
                    <td>{new Date(result.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : query.data ? (
          <Empty>尚无已发布结果。成功完成的计算将在此显示。</Empty>
        ) : null}
      </Panel>
    </>
  );
}
export function ResultDetail() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  const query = useQuery({
    queryKey: ["result-content", projectId, id],
    queryFn: ({ signal }) =>
      request(
        "/results/" + encodeURIComponent(id) + "/content",
        payloadSchema,
        { signal },
      ),
  });
  const result = query.data;
  return (
    <>
      <Link to="/results">← 返回结果中心</Link>
      <PageTitle
        title="结果与科研追溯"
        description={id}
        actions={
          <a
            className="button secondary"
            href={"/api/v1/results/" + encodeURIComponent(id) + "/content"}
            download={"coastmas-result-" + id + ".json"}
          >
            下载完整结果
          </a>
        }
      />
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      {result ? (
        <>
          <div className="metrics">
            <div className="metric">
              <span>实际计算耗时</span>
              <strong>{result.elapsed_seconds.toFixed(2)} s</strong>
            </div>
            <div className="metric">
              <span>实际执行节点</span>
              <strong>{result.executed_nodes.length}</strong>
            </div>
            <div className="metric">
              <span>执行阶段 LLM 调用</span>
              <strong>{result.llm_calls}</strong>
            </div>
          </div>
          {Object.entries(result.outputs).map(([name, value]) => (
            <Panel key={name} title={name}>
              <ResultValue value={value} />
            </Panel>
          ))}
          <Panel title="来源与复现">
            <dl className="definition-grid">
              <div>
                <dt>工作流</dt>
                <dd>
                  {result.run_manifest.workflow.name} · v
                  {result.run_manifest.workflow.version}
                </dd>
              </div>
              <div>
                <dt>场景</dt>
                <dd>
                  {result.run_manifest.scene.name} · v
                  {result.run_manifest.scene.version}
                </dd>
              </div>
              <div>
                <dt>随机种子</dt>
                <dd>{result.run_manifest.random_seed}</dd>
              </div>
              <div>
                <dt>软件版本</dt>
                <dd>{result.run_manifest.software_version}</dd>
              </div>
            </dl>
            <p className="break">输入指纹：{result.input_fingerprint}</p>
            <Details title="完整运行清单" value={result.run_manifest} />
          </Panel>
        </>
      ) : null}
    </>
  );
}
function ResultValue({ value }: { value: unknown }) {
  const geographic = geographicCollection.safeParse(value);
  if (geographic.success)
    return (
      <Suspense fallback={<Loading />}>
        <GeoMap data={geographic.data} />
      </Suspense>
    );
  const statistics = coastalStatistics.safeParse(value);
  if (statistics.success)
    return (
      <Suspense fallback={<Loading />}>
        <CoastalStatistics data={statistics.data} />
      </Suspense>
    );
  const rows = z.array(z.record(z.string(), z.unknown())).safeParse(value);
  if (rows.success && rows.data.length > 0) {
    const columns = [
      ...new Set(rows.data.flatMap((row) => Object.keys(row))),
    ].slice(0, 20);
    return (
      <>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.data.slice(0, 100).map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>{display(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {rows.data.length > 100 ? <p>显示前 100 行；完整数据可下载。</p> : null}
      </>
    );
  }
  const record = z.record(z.string(), z.unknown()).safeParse(value);
  if (record.success)
    return (
      <dl className="definition-grid">
        {Object.entries(record.data).map(([key, item]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{display(item)}</dd>
          </div>
        ))}
      </dl>
    );
  return <p className="break">{display(value)}</p>;
}
