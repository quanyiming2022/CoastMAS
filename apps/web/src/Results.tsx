import { DataTable } from "./components";
import { lazy, Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";
import { request, resultSchema } from "./api";
import { contract } from "./contracts";
import TemporalResultView from "./TemporalResultView";
import ProjectionResultView, { projectionResult } from "./ProjectionResultView";
const temporalResult = contract("TemporalResult");
import { payloadSchema } from "./result-payload";
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
import ManagementResults from "./ManagementResults";
const AssessmentResults = lazy(() => import("./AssessmentResults"));
import { opticalPreview } from "./imagery";
import { scientificLabel } from "./scientific-labels";

const GeoMap = lazy(() => import("./GeoMap"));
const CoastalStatistics = lazy(() => import("./CoastalStatistics"));
export default function Results() {
  const { projectId } = useWorkspace();
  return <ResultList key={projectId} projectId={projectId} />;
}
function ResultList({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const query = useQuery({
    queryKey: ["results", projectId, page],
    queryFn: ({ signal }) =>
      request(
        "/results?project_id=" +
          encodeURIComponent(projectId) +
          `&limit=50&offset=${page * 50}`,
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
        <p>选择两份不可变结果进行对照，先选左侧，再选右侧。</p>
        {selected.length === 2 ? (
          <Link
            className="button"
            to={`/results/compare?left=${encodeURIComponent(selected[0]!)}&right=${encodeURIComponent(selected[1]!)}`}
          >
            比较所选结果
          </Link>
        ) : (
          <p>已选择 {selected.length}/2 份结果</p>
        )}
        {selected.length ? (
          <button className="secondary" onClick={() => setSelected([])}>
            清空对比选择
          </button>
        ) : null}
        {query.data?.length ? (
          <DataTable>
            <thead>
              <tr>
                <th>对比</th>
                <th>结果</th>
                <th>任务</th>
                <th>生成时间</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((result) => (
                <tr key={result.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`选择对比 ${result.id}`}
                      checked={selected.includes(result.id)}
                      disabled={
                        result.result_type === "research_evaluation" ||
                        (selected.length >= 2 && !selected.includes(result.id))
                      }
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, result.id]
                            : current.filter((id) => id !== result.id),
                        )
                      }
                    />
                  </td>
                  <td>
                    <Link
                      to={
                        result.result_type === "research_evaluation"
                          ? "/research/" + encodeURIComponent(result.job_id)
                          : "/results/" + encodeURIComponent(result.id)
                      }
                    >
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
          </DataTable>
        ) : query.data ? (
          <Empty>尚无已发布结果。成功完成的计算将在此显示。</Empty>
        ) : null}
        <div className="pagination">
          <button
            className="secondary"
            disabled={page === 0}
            onClick={() => setPage((current) => current - 1)}
          >
            上一页结果
          </button>
          <span>第 {page + 1} 页</span>
          <button
            className="secondary"
            disabled={(query.data?.length ?? 0) < 50}
            onClick={() => setPage((current) => current + 1)}
          >
            下一页结果
          </button>
        </div>
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
            <Panel key={name} title={scientificLabel(name)}>
              <ResultValue value={value} />
            </Panel>
          ))}
          {result.result_view ? (
            <ManagementResults
              key={id}
              view={result.result_view}
              geometries={result.result_entity_geometries}
            />
          ) : (
            <p>此历史结果尚无实体绑定清单；原始结果及来源保持可用。</p>
          )}
          {result.result_view ? (
            <Suspense fallback={<Loading />}>
              <AssessmentResults key={id} view={result.result_view} />
            </Suspense>
          ) : null}
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
export function ResultValue({ value }: { value: unknown }) {
  const projection = projectionResult.safeParse(value);
  if (projection.success) return <ProjectionResultView result={projection.data} />;
  const temporal = temporalResult.safeParse(value);
  if (temporal.success) return <TemporalResultView result={temporal.data} />;
  const preview = opticalPreview.safeParse(value);
  if (preview.success) {
    const image = preview.data;
    const [west, south, east, north] = image.bounds;
    return (
      <>
        <p>
          {image.label} · 固定色标 {image.minimum} 至 {image.maximum} ·
          无数据透明
        </p>
        <Suspense fallback={<Loading />}>
          <GeoMap
            label="遥感计算结果地图"
            data={{
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  properties: { layer_kind: "raster_boundary" },
                  geometry: {
                    type: "Polygon",
                    coordinates: [
                      [
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                        [west, south],
                      ],
                    ],
                  },
                },
              ],
            }}
            images={[
              {
                ...image,
                acquired_at: "运行清单所列采集日期",
                attribution: "CoastMAS 指数计算；输入 Copernicus Sentinel-2",
              },
            ]}
          />
        </Suspense>
      </>
    );
  }
  const matrix = z.array(z.array(z.number().nullable())).safeParse(value);
  if (matrix.success && matrix.data.length)
    return (
      <p>
        栅格矩阵：{matrix.data.length} 行 × {matrix.data[0]?.length}{" "}
        列。完整数值、无数据标记和网格见结果下载。
      </p>
    );
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
        <DataTable>
          <thead>
            <tr>
              {columns.map((column) => (
                <th
                  key={column}
                  className={
                    rows.data.some((row) => typeof row[column] === "number") &&
                    rows.data.every(
                      (row) =>
                        row[column] == null || typeof row[column] === "number",
                    )
                      ? "numeric"
                      : undefined
                  }
                >
                  {scientificLabel(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.data.slice(0, 100).map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td
                    key={column}
                    className={
                      typeof row[column] === "number" ? "numeric" : undefined
                    }
                  >
                    {display(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </DataTable>

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
            <dt>{scientificLabel(key)}</dt>
            <dd>{display(item)}</dd>
          </div>
        ))}
      </dl>
    );
  return <p className="break">{display(value)}</p>;
}
