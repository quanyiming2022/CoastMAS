import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import type { FeatureCollection, Geometry } from "geojson";
import { api, APIError } from "./api";
import { EntityResults, collectionSchema } from "./EntityResults";
import { useViewState, type DisplayState } from "./useViewState";
import { useResearchPanel } from "./ResearchPanels";
import { LayerCatalog } from "./LayerCatalog";
import { ErrorNotice } from "./shared";
import type { VectorControls, VectorStatus } from "./VectorMap";
const emptyDisplay: DisplayState = {
  asset_id: null,
  band: 1,
  camera: null,
  visible: true,
  opacity: 0.9,
};
const VectorMap = lazy(() => import("./VectorMap"));
function VectorLegend({ property }: { property?: string }) {
  return (
    <div className="vector-legend" aria-label="矢量图例">
      {property === "assessment_score" ? (
        <>
          <span style={{ background: "#2c7bb6" }}>0</span>
          <span style={{ background: "#ffffbf" }}>0.5</span>
          <span style={{ background: "#d7191c" }}>1</span> 评价得分
        </>
      ) : property === "selected" ? (
        <>
          <span style={{ background: "#087f8c" }}>选入</span>
          <span style={{ background: "#aebdc2" }}>其他状态见属性</span>
        </>
      ) : (
        <>
          <span style={{ background: "#087f8c" }}>要素范围</span> · 统一颜色
        </>
      )}
    </div>
  );
}
const descriptor = z.object({
  draft_revision: z.number(),
  business_validated: z.boolean(),
});
export function VectorResult({
  jobId,
  data,
  layerHost,
  currentRevision,
  historical = false,
  title = "矢量成果",
}: {
  jobId: string;
  data: unknown;
  layerHost?: HTMLElement | null;
  currentRevision?: number;
  historical?: boolean;
  title?: string;
}) {
  const parsed = collectionSchema.safeParse(data);
  if (!parsed.success)
    return <p role="alert">此运行的空间成果结构无效，不能用原始资料替代。</p>;
  return (
    <Content
      key={jobId}
      jobId={jobId}
      data={
        parsed.data as FeatureCollection<Geometry> & { theme_property?: string }
      }
      layerHost={layerHost}
      currentRevision={currentRevision}
      historical={historical}
      title={title}
    />
  );
}
function Content({
  jobId,
  data,
  layerHost,
  currentRevision,
  historical,
  title,
}: {
  jobId: string;
  data: FeatureCollection<Geometry> & { theme_property?: string };
  layerHost?: HTMLElement | null;
  currentRevision?: number;
  historical: boolean;
  title: string;
}) {
  const panel = useResearchPanel(),
    owner = `/jobs/${jobId}/vector`,
    view = useViewState(`/jobs/${jobId}/view-state`);
  const state = view.active ?? emptyDisplay;
  const current = useRef(state);
  useEffect(() => {
    current.current = state;
  }, [state]);
  const controls = useRef<VectorControls | null>(null);
  const [status, setStatus] = useState<VectorStatus>({
    ready: false,
    offline: false,
    error: false,
  });
  const selected = state.selected_feature_id ?? null;
  const [fallback, setFallback] = useState<
    "style" | "details" | "pixel" | null
  >(null);
  const meta = useQuery({
    queryKey: ["vector-result-identity", jobId],
    queryFn: () => api(`/jobs/${jobId}/descriptor`, descriptor),
  });
  const saveView = view.save;
  const save = useCallback(
    (change: Partial<DisplayState>) => {
      const next = { ...current.current, ...change };
      current.current = next;
      void saveView(next).catch(() => {});
    },
    [saveView],
  );
  const onCamera = useCallback(
    (camera: NonNullable<DisplayState["camera"]>) => save({ camera }),
    [save],
  );
  const saveStatus =
    view.error instanceof APIError && view.error.status === 409
      ? "保存冲突"
      : view.error
        ? "保存失败"
        : !view.ready
          ? "正在恢复…"
          : view.saving
            ? "保存中…"
            : "已保存";
  const report = panel?.reportViewSave;
  useEffect(() => {
    report?.(jobId, saveStatus);
  }, [report, jobId, saveStatus]);
  function open(kind: "style" | "details" | "pixel", trigger?: HTMLElement) {
    if (panel) panel.open({ kind, owner }, trigger);
    else setFallback(kind);
  }
  const active =
    panel?.active &&
    panel.active.kind !== "step" &&
    panel.active.owner === owner
      ? panel.active.kind
      : panel
        ? null
        : fallback;
  const feature = data.features.find((f) => String(f.id) === selected);
  const present = state.vector_present ?? true;
  const layer = {
    id: "vector",
    name: title,
    kind: "矢量",
    role: title === "规划单元" ? "planning_units" : "result",
    visible: state.visible,
  };
  const layers = (
    <LayerCatalog
      items={present ? [layer] : []}
      available={present ? [] : [layer]}
      onAdd={() => save({ vector_present: true, visible: true })}
      activeId="vector"
      onSelect={() => open("details")}
      onVisibility={(_, visible) => save({ visible })}
      onOrder={() => {}}
      onRemove={() => save({ vector_present: false })}
      onAction={(_, action, trigger) => {
        if (action === "locate") controls.current?.locate();
        else if (action === "download") {
          const a = document.createElement("a");
          a.href = `/api/jobs/${jobId}/bundle`;
          a.download = "";
          a.click();
        } else open(action === "style" ? "style" : "details", trigger);
      }}
    />
  );
  const detail = (
    <>
      {active === "style" ? (
        <section aria-label="成果样式">
          <h3>成果样式</h3>
          <label className="check-label">
            <input
              type="checkbox"
              checked={state.legend_visible ?? false}
              onChange={(e) => save({ legend_visible: e.target.checked })}
            />
            显示地图图例
          </label>
          <VectorLegend property={data.theme_property} />
          <label>
            不透明度
            <input
              type="range"
              min="0"
              max="1"
              step=".05"
              value={state.opacity}
              onChange={(e) => save({ opacity: Number(e.target.value) })}
            />
          </label>
          <p>
            橙色边线为当前点查对象。范围、属性及图例固定在本次运行；不推测缺失数值。
          </p>
        </section>
      ) : null}
      {active === "pixel" ? (
        <section aria-label="点查结果">
          <h3>单元 {selected}</h3>
          {feature ? (
            <dl>
              {Object.entries(feature.properties ?? {}).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>
                    {typeof v === "object" ? (
                      <details>
                        <summary>原始属性</summary>
                        <pre>{JSON.stringify(v, null, 2)}</pre>
                      </details>
                    ) : v === null ? (
                      "不适用/未知"
                    ) : (
                      String(v)
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>尚未选择空间对象</p>
          )}
        </section>
      ) : null}
      {active === "details" ? (
        <section aria-label="固定运行详情">
          <h3>{title}</h3>
          <p>
            本次产物含 {data.features.length} 个实际对象。
            {title === "规划单元"
              ? "规划单元准备不等于现状诊断或规划求解。"
              : "来源与数值固定于本次运行。"}
          </p>
          <p>
            运行 <code>{jobId}</code> · 配置 v{meta.data?.draft_revision}
          </p>
          <button
            type="button"
            className="text-button"
            onClick={() =>
              void navigator.clipboard
                .writeText(jobId)
                .catch(() => setFallback("details"))
            }
          >
            复制运行ID
          </button>
          {!meta.data?.business_validated ? (
            <p>工程结果尚未完成业务验证。</p>
          ) : null}
          <EntityResults data={data} tableOnly />
        </section>
      ) : null}
    </>
  );
  return (
    <div className="vector-result compact-result" aria-label="本次实际空间成果">
      <ErrorNotice error={view.error ?? meta.error} />
      {view.error ? (
        <button
          type="button"
          onClick={() => void view.restore().catch(() => {})}
        >
          重新读取已保存视图
        </button>
      ) : null}
      <div role="toolbar" aria-label="成果工具条" className="result-toolbar">
        <strong className="result-title" title={title}>
          {title}
        </strong>
        <span className="run-identity" title={jobId}>
          {historical ? "历史运行" : "运行"} {jobId.slice(0, 8)} · v
          {meta.data?.draft_revision ?? "…"}
        </span>
        {currentRevision &&
        meta.data &&
        currentRevision > meta.data.draft_revision ? (
          <span className="status-chip">草稿已更新</span>
        ) : null}
        <span
          role="status"
          aria-label={
            status.error
              ? "矢量显示失败"
              : !(present && state.visible)
                ? "矢量图层隐藏"
                : status.ready
                  ? "矢量图层就绪"
                  : "正在绘制矢量"
          }
        >
          {status.error
            ? "显示失败"
            : !(present && state.visible)
              ? "已隐藏"
              : status.ready
                ? "✓"
                : "加载中"}
        </span>
        {status.offline ? (
          <span className="scientific-status">底图离线</span>
        ) : null}
        {!meta.data?.business_validated ? (
          <span className="scientific-status">工程结果 · 待验证</span>
        ) : null}
        {data.features.length > 5000 ? (
          <span className="scientific-status">
            有界预览5000/{data.features.length}
          </span>
        ) : null}
        <button
          type="button"
          className="secondary"
          onClick={() => controls.current?.locate()}
        >
          定位
        </button>
        <button
          type="button"
          className="secondary"
          onClick={(e) => open("style", e.currentTarget)}
        >
          样式
        </button>
        <button
          type="button"
          className="secondary"
          onClick={(e) => open("details", e.currentTarget)}
        >
          详情
        </button>
        <a
          className="button secondary"
          href={`/api/jobs/${jobId}/bundle`}
          download
        >
          导出
        </a>
      </div>
      {view.ready ? (
        <Suspense fallback={<p role="status">正在加载成果地图…</p>}>
          <VectorMap
            compact
            data={data}
            themeProperty={data.theme_property}
            selected={selected}
            onSelect={(id) => {
              save({ selected_feature_id: id });
              open("pixel");
            }}
            camera={state.camera}
            onCamera={onCamera}
            controlsRef={controls}
            onStatus={setStatus}
            visible={present && state.visible}
            opacity={state.opacity}
          />
        </Suspense>
      ) : null}
      {present && state.visible && state.legend_visible ? (
        <div className="vector-map-legend">
          <VectorLegend property={data.theme_property} />
        </div>
      ) : null}
      {layerHost ? createPortal(layers, layerHost) : layers}
      {panel?.host ? (
        createPortal(detail, panel.host)
      ) : fallback ? (
        <aside>
          <button type="button" onClick={() => setFallback(null)}>
            关闭详情
          </button>
          {detail}
        </aside>
      ) : null}
    </div>
  );
}
