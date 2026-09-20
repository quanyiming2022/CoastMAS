import {
  lazy,
  Suspense,
  useCallback,
  useMemo,
  useState,
  type ChangeEvent,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema } from "./api";
import { contract, sceneContract } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  Details,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";
import { geographicCollection } from "./result-data";
import { aoiFromUpload, closeDrawing } from "./scene-editor";
import type { SceneSpec, JsonValue } from "./generated/contracts";
import ScientificFields from "./ScientificFields";
import ReferencePicker from "./ReferencePicker";
import SceneRun from "./SceneRun";
const GeoMap = lazy(() => import("./GeoMap"));
const inspectionContract = contract("SceneInspection");

export default function SceneWorkspace() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  const [version, setVersion] = useState("");
  const query = useQuery({
    queryKey: ["scene-workspace", projectId, id, version],
    enabled: !!id,
    queryFn: async ({ signal }) =>
      sceneContract.parse(
        (
          await request(
            `/scenes/${encodeURIComponent(id!)}${version ? `?version=${encodeURIComponent(version)}` : ""}`,
            revisionSchema,
            { signal },
          )
        ).spec,
      ),
  });
  return (
    <>
      <Link to="/scenes">← 返回场景目录</Link>
      {id ? (
        <label>
          读取场景版本
          <input
            type="number"
            min={1}
            value={version}
            placeholder="当前版本"
            onChange={(event) => setVersion(event.target.value)}
          />
        </label>
      ) : null}
      <ErrorNotice error={query.error} />
      {id && query.isPending ? (
        <Loading />
      ) : !id || query.data ? (
        <Editor
          key={`${id ?? "new"}:${query.data?.version ?? 0}`}
          initial={query.data}
          onSaved={() => setVersion("")}
        />
      ) : null}
    </>
  );
}
function Editor({
  initial,
  onSaved,
}: {
  initial?: SceneSpec;
  onSaved: () => void;
}) {
  const { projectId } = useWorkspace();
  const client = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<SceneSpec>(
    () =>
      initial ?? {
        id: `scene-${crypto.randomUUID()}`,
        name: "新场景",
        version: 1,
        management_goal: "",
        study_area: {},
        entity_types: [],
        time_range: { start: "", end: "" },
        scenario_conditions: {},
        constraints: [],
        required_outputs: [],
        data_policy: { study_area_crs: "EPSG:4326" },
        quality_requirements: {},
        entity_references: [],
        data_references: [],
      },
  );
  const [drawing, setDrawing] = useState(false);
  const [entityTypesText, setEntityTypesText] = useState(
    initial?.entity_types.join(", ") ?? "",
  );
  const [outputsText, setOutputsText] = useState(
    initial?.required_outputs.join(", ") ?? "",
  );
  const [points, setPoints] = useState<[number, number][]>([]);
  const [error, setError] = useState<Error | null>(null);
  const signature = JSON.stringify(draft);
  const unchanged = !!initial && signature === JSON.stringify(initial);
  const inspect = useMutation({
    mutationFn: async () => ({
      signature,
      report: await request("/scene-drafts/inspect", inspectionContract, {
        method: "POST",
        body: { project_id: projectId, scene: sceneContract.parse(draft) },
      }),
    }),
  });
  const report =
    inspect.data?.signature === signature ? inspect.data.report : undefined;
  const background = useQuery({
    queryKey: ["scene-background", projectId],
    queryFn: ({ signal }) =>
      request(
        `/entities/spatial?project_id=${encodeURIComponent(projectId)}&west=-180&south=-90&east=180&north=90&limit=500`,
        geographicCollection.extend({ has_more: z.boolean() }),
        { signal },
      ),
  });
  const mapData = useMemo(() => {
    const features: unknown[] = [...(background.data?.features ?? [])];
    if (report) {
      features.push({
        type: "Feature",
        properties: { layer_kind: "aoi" },
        geometry: report.study_area_wgs84,
      });
      for (const row of report.data_coverage)
        if (row.footprint_wgs84)
          features.push({
            type: "Feature",
            properties: { layer_kind: "coverage", name: row.name },
            geometry: row.footprint_wgs84,
          });
    } else if (
      draft.data_policy.study_area_crs === "EPSG:4326" &&
      Object.keys(draft.study_area).length
    ) {
      const candidate = geographicCollection.safeParse({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { layer_kind: "aoi" },
            geometry: draft.study_area,
          },
        ],
      });
      if (candidate.success) features.push(...candidate.data.features);
    }
    for (const point of points)
      features.push({
        type: "Feature",
        properties: { layer_kind: "drawing" },
        geometry: { type: "Point", coordinates: point },
      });
    if (points.length >= 2)
      features.push({
        type: "Feature",
        properties: { layer_kind: "drawing" },
        geometry: { type: "LineString", coordinates: points },
      });
    return geographicCollection.parse({ type: "FeatureCollection", features });
  }, [
    background.data,
    draft.data_policy.study_area_crs,
    draft.study_area,
    points,
    report,
  ]);
  const onMapClick = useCallback(
    (point: [number, number]) => {
      if (drawing) setPoints((current) => [...current, point]);
    },
    [drawing],
  );
  const save = useMutation({
    mutationFn: async (copy: boolean) => {
      const spec = sceneContract.parse({
        ...draft,
        id: copy ? `scene-${crypto.randomUUID()}` : draft.id,
        name: copy ? draft.name + " 副本" : draft.name,
        version: copy ? 1 : (initial?.version ?? 0) + 1,
      });
      // Geometry/CRS must be parseable; catalog coverage warnings remain visible and
      // do not pretend to replace the workflow's scientific execution checks.
      await request("/scene-drafts/inspect", inspectionContract, {
        method: "POST",
        body: { project_id: projectId, scene: spec },
      });
      const result = await request(
        initial && !copy
          ? `/scenes/${encodeURIComponent(initial.id)}`
          : "/scenes",
        revisionSchema,
        {
          method: initial && !copy ? "PUT" : "POST",
          body:
            initial && !copy
              ? { expected_version: initial.version, spec }
              : { project_id: projectId, spec },
        },
      );
      return sceneContract.parse(result.spec);
    },
    onSuccess: async (spec) => {
      client.setQueryData(["scene-workspace", projectId, spec.id, ""], spec);
      onSaved();
      navigate(`/scenes/${encodeURIComponent(spec.id)}/workspace`);
      await client.invalidateQueries({ queryKey: ["scenes", projectId] });
      await client.invalidateQueries({
        queryKey: ["scene-selection", projectId],
      });
    },
  });
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 8 * 1024 * 1024)
        throw new Error("AOI 文件超过 8 MB 限制");
      const geometry = aoiFromUpload(JSON.parse(await file.text()));
      setDraft((current) => ({
        ...current,
        study_area: geometry,
        data_policy: { ...current.data_policy, study_area_crs: "EPSG:4326" },
      }));
      setPoints([]);
      setDrawing(false);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause : new Error("AOI 读取失败"));
    }
  }
  function changePolicy(values: Record<string, JsonValue>) {
    setDraft((current) => ({
      ...current,
      data_policy: {
        ...values,
        study_area_crs: current.data_policy.study_area_crs ?? "EPSG:4326",
      },
    }));
  }
  const policyFields = Object.fromEntries(
    Object.entries(draft.data_policy).filter(
      ([key]) => key !== "study_area_crs",
    ),
  );
  return (
    <>
      <PageTitle
        title="场景工作台"
        description="在地图中定义分析范围，固定地理实体与数据版本，并连接实际工作流和结果。"
      />
      <ErrorNotice
        error={error ?? background.error ?? inspect.error ?? save.error}
      />
      <fieldset className="scene-form" disabled={save.isPending}>
        <div className="toolbar">
          <label>
            场景名称
            <input
              value={draft.name}
              onChange={(event) =>
                setDraft({ ...draft, name: event.target.value })
              }
            />
          </label>
          <label>
            管理目标
            <input
              value={draft.management_goal}
              onChange={(event) =>
                setDraft({ ...draft, management_goal: event.target.value })
              }
            />
          </label>
          <button onClick={() => save.mutate(false)} disabled={drawing}>
            保存场景版本
          </button>
          <button
            className="secondary"
            onClick={() => save.mutate(true)}
            disabled={drawing}
          >
            复制场景
          </button>
        </div>
        <Panel title="研究范围与地理实体">
          <div className="toolbar">
            <button
              className="secondary"
              onClick={() => {
                setDrawing(true);
                setPoints([]);
              }}
            >
              开始绘制 AOI
            </button>
            <button
              disabled={!drawing || points.length < 3}
              onClick={() => {
                try {
                  const geometry = closeDrawing(points);
                  setDraft((current) => ({
                    ...current,
                    study_area: geometry,
                    data_policy: {
                      ...current.data_policy,
                      study_area_crs: "EPSG:4326",
                    },
                  }));
                  setDrawing(false);
                  setPoints([]);
                  setError(null);
                } catch (cause) {
                  setError(
                    cause instanceof Error ? cause : new Error("绘制失败"),
                  );
                }
              }}
            >
              完成 AOI
            </button>
            <button
              className="secondary"
              disabled={!drawing || !points.length}
              onClick={() => setPoints((current) => current.slice(0, -1))}
            >
              撤销顶点
            </button>
            <button
              className="secondary"
              disabled={!drawing}
              onClick={() => {
                setDrawing(false);
                setPoints([]);
              }}
            >
              取消绘制
            </button>
            <label>
              上传 AOI（WGS 84 GeoJSON）
              <input
                type="file"
                accept=".json,.geojson,application/geo+json"
                onChange={(event) => void upload(event)}
              />
            </label>
          </div>
          <p>
            {drawing
              ? `绘制中：已选择 ${points.length} 个顶点。点击地图添加，至少三个顶点后完成。`
              : "橙色：AOI；绿色：项目实体；蓝色：所选数据目录范围。覆盖不代表有效像元或观测质量。"}
          </p>
          <Suspense fallback={<Loading />}>
            <GeoMap
              data={mapData}
              label="场景研究范围地图"
              onMapClick={onMapClick}
              fitData={!drawing}
            />
          </Suspense>
          {background.data?.has_more ? (
            <p>
              背景只显示前 500
              个实体；下方实体选择支持分页，已选版本在覆盖检查中验证。
            </p>
          ) : null}
          <label>
            AOI 坐标系
            <input
              value={String(draft.data_policy.study_area_crs ?? "")}
              disabled={drawing}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  data_policy: {
                    ...current.data_policy,
                    study_area_crs: event.target.value,
                  },
                }))
              }
            />
          </label>
          <ReferencePicker
            endpoint="entities"
            title="地理实体"
            selected={draft.entity_references ?? []}
            onChange={(references) =>
              setDraft((current) => ({
                ...current,
                entity_references: references,
              }))
            }
          />
          <label>
            实体类型（逗号分隔）
            <input
              value={entityTypesText}
              onChange={(event) => {
                setEntityTypesText(event.target.value);
                setDraft((current) => ({
                  ...current,
                  entity_types: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                }));
              }}
            />
          </label>
        </Panel>
        <Panel title="时间与情景条件">
          <div className="toolbar">
            <label>
              开始时间（含时区）
              <input
                placeholder="2020-01-01T00:00:00Z"
                value={draft.time_range.start}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    time_range: {
                      ...current.time_range,
                      start: event.target.value,
                    },
                  }))
                }
              />
            </label>
            <label>
              结束时间（含时区）
              <input
                placeholder="2023-01-01T00:00:00Z"
                value={draft.time_range.end}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    time_range: {
                      ...current.time_range,
                      end: event.target.value,
                    },
                  }))
                }
              />
            </label>
          </div>
          <ScientificFields
            title="情景条件"
            values={draft.scenario_conditions}
            onChange={(values) =>
              setDraft((current) => ({
                ...current,
                scenario_conditions: values,
              }))
            }
          />
          <ScientificFields
            title="数据策略"
            values={policyFields}
            onChange={changePolicy}
          />
          <ScientificFields
            title="质量要求"
            values={draft.quality_requirements}
            onChange={(values) =>
              setDraft((current) => ({
                ...current,
                quality_requirements: values,
              }))
            }
          />
          <label>
            所需输出（逗号分隔）
            <input
              value={outputsText}
              onChange={(event) => {
                setOutputsText(event.target.value);
                setDraft((current) => ({
                  ...current,
                  required_outputs: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                }));
              }}
            />
          </label>
        </Panel>
        <Panel title="数据选择与覆盖">
          <ReferencePicker
            endpoint="data-assets"
            title="数据"
            selected={draft.data_references ?? []}
            onChange={(references) =>
              setDraft((current) => ({
                ...current,
                data_references: references,
              }))
            }
          />
          <button
            disabled={inspect.isPending || drawing}
            onClick={() => inspect.mutate()}
          >
            检查场景与数据覆盖
          </button>
          {report ? (
            <>
              <Status value={report.valid ? "VALIDATED" : "MANUAL_REVIEW"} />
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>资源版本</th>
                      <th>空间覆盖</th>
                      <th>时间覆盖</th>
                      <th>状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...report.data_coverage, ...report.entity_coverage].map(
                      (row) => (
                        <tr key={row.reference.id}>
                          <td>
                            {row.name} · v{row.reference.version}
                          </td>
                          <td>
                            {row.spatial_fraction === null
                              ? "未提供比例 / 实体采用相交检查"
                              : `${(row.spatial_fraction * 100).toFixed(2)}%`}
                          </td>
                          <td>
                            {row.temporal_coverage === null
                              ? "未知"
                              : row.temporal_coverage
                                ? "覆盖"
                                : "不完整"}
                          </td>
                          <td>
                            {
                              {
                                COVERED: "覆盖",
                                PARTIAL: "部分覆盖",
                                OUTSIDE: "范围外",
                                UNKNOWN: "未知",
                              }[row.status]
                            }
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
              {report.issues.length ? (
                <Details title="覆盖检查说明" value={report.issues} />
              ) : null}
            </>
          ) : (
            <p className="muted">
              使用当前草稿重新检查；没有元数据的覆盖保持未知。
            </p>
          )}
        </Panel>
      </fieldset>
      {initial && unchanged ? (
        <SceneRun scene={initial} />
      ) : (
        <Panel title="预检与执行">
          <p>先保存当前场景版本，再选择工作流预检和执行。</p>
        </Panel>
      )}
      <Details title="场景约束及版本契约" value={draft} />
    </>
  );
}
