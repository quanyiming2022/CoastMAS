import {
  lazy,
  Suspense,
  useId,
  useEffect,
  useState,
  useRef,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { APIError } from "./api";
import type { MapDisplayStatus } from "./AssetMap";
import { LayerCatalog } from "./LayerCatalog";
import { useResearchPanel } from "./ResearchPanels";
import { ErrorNotice } from "./shared";
import { useViewState } from "./useViewState";
import type { MapControls } from "./AssetMap";
const AssetMap = lazy(() => import("./AssetMap"));
const artifact = z.object({
  id: z.string(),
  name: z.string(),
  title: z.string().optional(),
  role: z.string(),
  sha256: z.string(),
  resource: z.string(),
  view_kind: z.string(),
  legend: z
    .array(
      z.object({ value: z.number(), label: z.string(), color: z.string() }),
    )
    .optional(),
});
const statistics = z.object({
  total_pixels: z.number(),
  valid_pixels: z.number(),
  invalid_pixels: z.number(),
  scope: z.literal("full_grid"),
  minimum: z.number().optional(),
  maximum: z.number().optional(),
  mean: z.number().optional(),
  histogram: z
    .object({ edges: z.array(z.number()), counts: z.array(z.number()) })
    .optional(),
});
const descriptorSchema = z.object({
  run_id: z.string(),
  draft_revision: z.number(),
  primary: artifact.nullable(),
  outputs: z.array(artifact),
  statistics: statistics.nullable(),
  business_validated: z.boolean().default(false),
});
function Statistics({ value }: { value: z.infer<typeof statistics> }) {
  return (
    <section aria-label="综合得分全域分布">
      <h3>全域统计</h3>
      <dl className="result-statistics" aria-label="全域覆盖统计">
        <dt>全域像元</dt>
        <dd>{value.total_pixels.toLocaleString()}</dd>
        <dt>有效</dt>
        <dd>{value.valid_pixels.toLocaleString()}</dd>
        <dt>无效</dt>
        <dd>{value.invalid_pixels.toLocaleString()}</dd>
      </dl>
      {value.histogram ? (
        <>
          <p>
            最小值 {value.minimum?.toPrecision(7)} · 最大值{" "}
            {value.maximum?.toPrecision(7)} · 均值 {value.mean?.toPrecision(7)}
          </p>
          <svg
            role="img"
            aria-label="全域综合得分直方图"
            viewBox="0 0 440 120"
            className="result-histogram"
          >
            {value.histogram.counts.map((count, index, counts) => (
              <rect
                key={index}
                x={index * 22}
                y={100 - (count / Math.max(...counts, 1)) * 96}
                width="20"
                height={(count / Math.max(...counts, 1)) * 96}
                fill="#087f8c"
              >
                <title>
                  {value.histogram!.edges[index]!.toFixed(2)} 至{" "}
                  {value.histogram!.edges[index + 1]!.toFixed(2)}：{count} 像元
                </title>
              </rect>
            ))}
          </svg>
          <details>
            <summary>查看实际统计表</summary>
            <table aria-label="成果全域分布">
              <thead>
                <tr>
                  <th>得分区间（末区间含上限）</th>
                  <th>实际像元数</th>
                </tr>
              </thead>
              <tbody>
                {value.histogram.counts.map((count, index) => (
                  <tr key={index}>
                    <td>
                      {value.histogram!.edges[index]!.toFixed(2)} —{" "}
                      {value.histogram!.edges[index + 1]!.toFixed(2)}
                    </td>
                    <td>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      ) : null}
    </section>
  );
}
export function ResultArtifact({
  jobId,
  layerHost,
  currentRevision,
  historical = false,
  supplementary,
  scopeNotice,
}: {
  jobId: string;
  layerHost?: HTMLElement | null;
  currentRevision?: number;
  historical?: boolean;
  supplementary?: ReactNode;
  scopeNotice?: string;
}) {
  const sharedPanel = useResearchPanel();
  const [mapStatus, setMapStatus] = useState<MapDisplayStatus>({
    state: "loading",
    message: "正在加载图层",
    offline: false,
  });
  const mapControls = useRef<MapControls | null>(null);
  const descriptor = useQuery({
    queryKey: ["result-descriptor", jobId],
    queryFn: () => api(`/jobs/${jobId}/descriptor`, descriptorSchema),
  });
  const view = useViewState(`/jobs/${jobId}/view-state`);
  const state = view.active ?? {
    asset_id: null,
    band: 1,
    camera: null,
    visible: true,
    opacity: 0.9,
  };
  const [detailsOpen, setDetailsOpen] = useState(false),
    [copyStatus, setCopyStatus] = useState("");
  const [point, setPoint] = useState<{
    longitude: number;
    latitude: number;
    band: number;
  } | null>(null);
  const anchorName = "--result-tools-" + useId().replace(/[^a-z0-9]/gi, "");
  const styleId = useId(),
    exportId = useId();
  const primary =
    descriptor.data?.outputs.find(
      (output) =>
        output.id === state.artifact_id && output.view_kind === "raster",
    ) ?? descriptor.data?.primary;
  const outputs =
    descriptor.data?.outputs.filter(
      (output) => output.view_kind === "raster",
    ) ?? [];
  const contributions = useQuery({
    queryKey: ["point-contributions", jobId, point],
    enabled: !!point && !!descriptor.data,
    queryFn: async () =>
      Promise.all(
        (
          descriptor.data?.outputs.filter(
            (output) => output.role === "contribution",
          ) ?? []
        ).map(async (output) => ({
          output,
          ...(await api(
            `${output.resource}/inspect`,
            z.object({
              value: z.number().nullable(),
              valid: z.boolean(),
              sha256: z.string(),
            }),
            { method: "POST", body: JSON.stringify({ ...point, band: 1 }) },
          )),
        })),
      ),
  });
  const save = (change: Partial<typeof state>) => {
    const current =
      state.layers ??
      outputs.map((output) => ({
        artifact_id: output.id,
        visible: output.id === primary?.id && state.visible,
        opacity: state.opacity,
      }));
    const layers =
      change.opacity !== undefined || change.visible !== undefined
        ? current.map((layer) =>
            layer.artifact_id === primary?.id
              ? {
                  ...layer,
                  opacity: change.opacity ?? layer.opacity,
                  visible: change.visible ?? layer.visible,
                }
              : layer,
          )
        : state.layers;
    void view
      .save({ ...state, ...change, ...(layers ? { layers } : {}) })
      .catch(() => {});
  };
  const viewSaveStatus =
    view.error instanceof APIError && view.error.status === 409
      ? "保存冲突"
      : view.error
        ? "保存失败"
        : !view.ready
          ? "正在恢复…"
          : view.saving
            ? "保存中…"
            : "已保存";
  const reportViewSave = sharedPanel?.reportViewSave;
  useEffect(() => {
    reportViewSave?.(jobId, viewSaveStatus);
  }, [reportViewSave, jobId, viewSaveStatus]);
  const placements =
    state.layers ??
    outputs.map((output) => ({
      artifact_id: output.id,
      visible: output.id === primary?.id && state.visible,
      opacity: state.opacity,
    }));
  const activePlacement = placements.find(
    (layer) => layer.artifact_id === primary?.id,
  );
  const stack = placements.flatMap((layer) => {
    const output = outputs.find((item) => item.id === layer.artifact_id);
    return output
      ? [{ ...layer, id: output.id, resource: output.resource, band: 1 }]
      : [];
  });
  const selectLayer = (
    id: string,
    showDetails = true,
    trigger?: HTMLElement,
  ) => {
    const output = outputs.find((item) => item.id === id);
    if (!output) return;
    void view
      .save({ ...state, artifact_id: id, band: 1, layers: placements })
      .catch(() => {});
    if (showDetails)
      sharedPanel?.open({ kind: "details", owner: output.resource }, trigger);
  };
  const layerItem = (output: (typeof outputs)[number]) => ({
    id: output.id,
    name: output.title ?? output.name,
    role: output.role,
    kind: output.view_kind === "raster" ? "栅格" : output.view_kind,
    visible:
      placements.find((layer) => layer.artifact_id === output.id)?.visible ??
      false,
  });
  const layers = (
    <LayerCatalog
      items={placements.flatMap((layer) => {
        const output = outputs.find((item) => item.id === layer.artifact_id);
        return output ? [layerItem(output)] : [];
      })}
      activeId={primary?.id}
      onSelect={(id) => selectLayer(id)}
      onVisibility={(id, visible) =>
        void view
          .save({
            ...state,
            layers: placements.map((layer) =>
              layer.artifact_id === id ? { ...layer, visible } : layer,
            ),
          })
          .catch(() => {})
      }
      onOrder={(ids) =>
        void view
          .save({
            ...state,
            layers: ids.flatMap(
              (id) =>
                placements.find((layer) => layer.artifact_id === id) ?? [],
            ),
          })
          .catch(() => {})
      }
      onRemove={(ids) =>
        void view
          .save({
            ...state,
            layers: placements.filter(
              (layer) => !ids.includes(layer.artifact_id),
            ),
          })
          .catch(() => {})
      }
      available={outputs
        .filter(
          (output) =>
            !placements.some((layer) => layer.artifact_id === output.id),
        )
        .map(layerItem)}
      onAdd={(id) =>
        void view
          .save({
            ...state,
            layers: [
              ...placements,
              { artifact_id: id, visible: true, opacity: 0.9 },
            ],
          })
          .catch(() => {})
      }
      onAction={(id, action, trigger) => {
        const output = outputs.find((item) => item.id === id);
        if (!output) return;
        if (action === "download") {
          const link = document.createElement("a");
          link.href = `/api${output.resource}/download`;
          link.download = "";
          link.click();
          return;
        }
        selectLayer(id, false);
        if (action === "locate") mapControls.current?.locate();
        else
          sharedPanel?.open(
            {
              kind: action === "style" ? "style" : "details",
              owner: output.resource,
            },
            trigger,
          );
      }}
    />
  );
  return (
    <div
      className="result-artifact compact-result"
      aria-label="本次实际空间成果"
    >
      <ErrorNotice error={descriptor.error ?? view.error} />
      {descriptor.isPending ? <p role="status">正在读取本次成果…</p> : null}
      {descriptor.error ? (
        <button type="button" onClick={() => void descriptor.refetch()}>
          重试成果显示
        </button>
      ) : null}
      {layerHost ? createPortal(layers, layerHost) : null}
      {primary && view.ready ? (
        <Suspense fallback={<p role="status">正在加载成果地图…</p>}>
          <AssetMap
            controls={mapControls}
            key={jobId}
            assetId={`${jobId}:map`}
            resource={descriptor.data!.primary!.resource}
            inspectionResource={primary.resource}
            overlayLayers={stack}
            legend={primary.legend}
            legendVisible={state.legend_visible ?? false}
            layerTitle={primary.title ?? primary.name}
            band={state.band}
            camera={state.camera}
            onCamera={(camera) => save({ camera })}
            visible={activePlacement?.visible ?? false}
            opacity={activePlacement?.opacity ?? state.opacity}
            onDisplay={save}
            chrome={{
              onStatus: setMapStatus,
              detailsOpen,
              onInspect: (p) => {
                setPoint(p);
                if (!sharedPanel) setDetailsOpen(true);
              },
              toolbar: (
                <div
                  role="toolbar"
                  aria-label="成果工具条"
                  className="result-toolbar"
                  style={{ anchorName }}
                >
                  {outputs.length > 1 ? (
                    <select
                      aria-label="成果图层"
                      value={primary.id}
                      onChange={(event) =>
                        selectLayer(event.target.value, false)
                      }
                    >
                      {outputs.map((output) => (
                        <option key={output.id} value={output.id}>
                          {output.title ?? output.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <strong
                      className="result-title"
                      title={primary.title ?? primary.name}
                    >
                      {primary.title ?? primary.name}
                    </strong>
                  )}
                  <span
                    className="run-identity"
                    title={`运行 ${jobId} · 配置 v${descriptor.data!.draft_revision}`}
                  >
                    {historical ? "历史运行" : "运行"} {jobId.slice(0, 8)} · v
                    {descriptor.data!.draft_revision}
                  </span>
                  {currentRevision &&
                  currentRevision > descriptor.data!.draft_revision ? (
                    <span className="status-chip">草稿已更新</span>
                  ) : null}
                  <span
                    className="result-layer-status"
                    data-state={mapStatus.state}
                    role="status"
                    aria-label={
                      mapStatus.state === "ready"
                        ? "图层就绪"
                        : mapStatus.message
                    }
                    title={mapStatus.message}
                  >
                    {mapStatus.state === "ready"
                      ? "✓"
                      : mapStatus.state === "loading"
                        ? "加载中"
                        : mapStatus.state === "hidden"
                          ? "已隐藏"
                          : mapStatus.state === "error"
                            ? "显示失败"
                            : "无定位"}
                  </span>
                  {mapStatus.offline ? (
                    <span
                      className="scientific-status"
                      title="互联网底图不可用；实际数据层独立显示。"
                    >
                      底图离线
                    </span>
                  ) : null}
                  {mapStatus.state === "error" ? (
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => mapControls.current?.retry()}
                    >
                      重试显示
                    </button>
                  ) : null}
                  {!descriptor.data!.business_validated ? (
                    <span
                      className="scientific-status"
                      title="工程结果，尚未完成独立精度与适用性等业务验证；完整依据见详情。"
                    >
                      工程结果 · 待验证
                    </span>
                  ) : null}
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => mapControls.current?.locate()}
                  >
                    定位
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    popoverTarget={sharedPanel ? undefined : styleId}
                    onClick={
                      sharedPanel
                        ? (event) =>
                            sharedPanel.active?.kind === "style" &&
                            sharedPanel.active.owner === primary.resource
                              ? sharedPanel.close()
                              : sharedPanel.open(
                                  { kind: "style", owner: primary.resource },
                                  event.currentTarget,
                                )
                        : undefined
                    }
                  >
                    样式
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    aria-expanded={
                      sharedPanel
                        ? (sharedPanel.active?.kind === "details" ||
                            sharedPanel.active?.kind === "pixel") &&
                          sharedPanel.active.owner === primary.resource
                        : detailsOpen
                    }
                    onClick={(event) =>
                      sharedPanel
                        ? (sharedPanel.active?.kind === "details" ||
                            sharedPanel.active?.kind === "pixel") &&
                          sharedPanel.active.owner === primary.resource
                          ? sharedPanel.close()
                          : sharedPanel.open(
                              { kind: "details", owner: primary.resource },
                              event.currentTarget,
                            )
                        : setDetailsOpen(!detailsOpen)
                    }
                  >
                    详情
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    popoverTarget={exportId}
                  >
                    导出
                  </button>
                </div>
              ),
              details: (
                <>
                  <section aria-label="固定运行详情">
                    <h3>固定运行与来源</h3>
                    {!descriptor.data!.business_validated ? (
                      <p>
                        工程结果，未认定业务有效性；计算成功不替代独立精度、方法适用性及科学依据验证。
                      </p>
                    ) : null}
                    {scopeNotice ? <p>{scopeNotice}</p> : null}
                    {mapStatus.offline ? (
                      <p>互联网底图不可用；实际数据层独立显示。</p>
                    ) : null}
                    <code>{jobId}</code>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() =>
                        void navigator.clipboard
                          .writeText(jobId)
                          .then(() => setCopyStatus("运行ID已复制"))
                          .catch(() =>
                            setCopyStatus("无法复制，请选择完整ID复制"),
                          )
                      }
                    >
                      复制运行ID
                    </button>
                    <span role="status">{copyStatus}</span>
                    <p>
                      配置 v{descriptor.data!.draft_revision}
                      ；查看历史不会覆盖当前草稿。
                    </p>
                    <p>文件 {primary.name}</p>
                    <code>{primary.sha256}</code>
                  </section>
                  {contributions.data?.length ? (
                    <section aria-label="本次原生像元贡献">
                      <h3>实际贡献值</h3>
                      <p>
                        与点查同一位置、同一固定运行；TOPSIS为加权坐标，不解释成得分加和。
                      </p>
                      <dl>
                        {contributions.data.map((item) => (
                          <div key={item.output.id}>
                            <dt>{item.output.title ?? item.output.name}</dt>
                            <dd>{item.valid ? item.value : "无有效值"}</dd>
                          </div>
                        ))}
                      </dl>
                    </section>
                  ) : null}
                  <ErrorNotice error={contributions.error} />
                  {descriptor.data?.statistics ? (
                    <Statistics value={descriptor.data.statistics} />
                  ) : null}
                  {supplementary}
                </>
              ),
            }}
          />
        </Suspense>
      ) : null}
      {sharedPanel?.host ? (
        createPortal(
          <div
            role="region"
            aria-label="成果样式"
            hidden={
              sharedPanel.active?.kind !== "style" ||
              sharedPanel.active.owner !== primary?.resource
            }
          >
            <h3>成果样式</h3>
            <label className="check-label">
              <input
                type="checkbox"
                checked={state.legend_visible ?? false}
                onChange={(event) =>
                  save({ legend_visible: event.target.checked })
                }
              />
              显示地图图例
            </label>
            <label>
              不透明度
              <input
                type="range"
                min="0"
                max="1"
                step=".05"
                value={activePlacement?.opacity ?? state.opacity}
                onChange={(event) =>
                  save({ opacity: Number(event.target.value) })
                }
              />
            </label>
            <p>仅改变显示；色带与视口不改变分析输入和原始数值。</p>
            {!layerHost ? (
              <label>
                <input
                  type="checkbox"
                  checked={activePlacement?.visible ?? false}
                  onChange={(event) => save({ visible: event.target.checked })}
                />
                显示当前图层
              </label>
            ) : null}
          </div>,
          sharedPanel.host,
        )
      ) : (
        <div
          id={styleId}
          popover="auto"
          role="dialog"
          aria-label="成果样式"
          className="result-popover"
          style={{ positionAnchor: anchorName }}
        >
          <h3>成果样式</h3>
          <label className="check-label">
            <input
              type="checkbox"
              checked={state.legend_visible ?? false}
              onChange={(event) =>
                save({ legend_visible: event.target.checked })
              }
            />
            显示地图图例
          </label>
          <label>
            不透明度
            <input
              type="range"
              min="0"
              max="1"
              step=".05"
              value={activePlacement?.opacity ?? state.opacity}
              onChange={(event) =>
                save({ opacity: Number(event.target.value) })
              }
            />
          </label>
          <p>仅改变显示；色带与视口不改变分析输入和原始数值。</p>
          {!layerHost ? (
            <label>
              <input
                type="checkbox"
                checked={activePlacement?.visible ?? false}
                onChange={(event) => save({ visible: event.target.checked })}
              />
              显示当前图层
            </label>
          ) : null}
        </div>
      )}
      <div
        id={exportId}
        popover="auto"
        role="dialog"
        aria-label="导出本次成果"
        className="result-popover"
        style={{ positionAnchor: anchorName }}
      >
        <h3>导出本次成果</h3>
        {primary ? (
          <p>
            <a href={`/api${primary.resource}/download`} download>
              下载实际成果
            </a>
          </p>
        ) : null}
        <p>
          <a href={`/api/jobs/${jobId}/bundle`} download>
            下载完整成果包
          </a>
        </p>
        <details>
          <summary>选择单项产物</summary>
          {descriptor.data?.outputs.map((output) => (
            <p key={output.id}>
              <a href={`/api/jobs/${jobId}/files/${output.id}`} download>
                {output.title ?? output.name}
              </a>
            </p>
          ))}
        </details>
        <p>全部链接固定到运行 {jobId.slice(0, 8)}，保留完整结果与来源清单。</p>
      </div>
    </div>
  );
}
