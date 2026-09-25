import {
  useEffect,
  useRef,
  useState,
  useId,
  useCallback,
  useImperativeHandle,
  type Ref,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useResearchPanel } from "./ResearchPanels";
import { Map, NavigationControl, ScaleControl, Marker } from "maplibre-gl";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { MapLegend } from "./MapLegend";
import type { RasterTileSource } from "maplibre-gl";
import { MapBoundary, baseMapStyle } from "./mapBase";
import { ErrorNotice } from "./shared";
import "maplibre-gl/dist/maplibre-gl.css";
const viewSchema = z.object({
  asset_id: z.string(),
  asset_revision: z.number(),
  sha256: z.string(),
  band: z.number(),
  band_count: z.number(),
  georeference_status: z.string(),
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
  display_status: z.string(),
  issues: z.array(z.string()),
  palette: z.record(z.string(), z.array(z.number())).nullable().optional(),
  minimum: z.number().nullable(),
  maximum: z.number().nullable(),
  sample_valid_pixels: z.number(),
  sample_pixels: z.number(),
  width: z.number(),
  height: z.number(),
  unit: z.string().nullable(),
});
const inspectSchema = z.object({
  asset_id: z.string(),
  asset_revision: z.number(),
  sha256: z.string(),
  band: z.number(),
  row: z.number(),
  column: z.number(),
  valid: z.boolean(),
  status: z.string(),
  stored_value: z.number().nullable(),
  value: z.number().nullable(),
  scale: z.number(),
  offset: z.number(),
  unit: z.string().nullable(),
});
export type Camera = { longitude: number; latitude: number; zoom: number };
export type MapDisplayStatus = {
  state: "loading" | "ready" | "hidden" | "error" | "unlocated";
  message: string;
  offline: boolean;
};
export type MapControls = { locate: () => void; retry: () => void };
export type RasterDisplayLayer = {
  id: string;
  resource: string;
  band: number;
  visible: boolean;
  opacity: number;
};
export type AssetMapProps = {
  legendVisible?: boolean;
  layerTitle?: string;
  inspectionResource?: string;
  overlayLayers?: RasterDisplayLayer[];
  controls?: Ref<MapControls>;
  chrome?: {
    onStatus?: (status: MapDisplayStatus) => void;
    toolbar: ReactNode;
    detailsOpen: boolean;
    details?: ReactNode;
    notices?: ReactNode;
    onInspect: (point: {
      longitude: number;
      latitude: number;
      band: number;
    }) => void;
  };
  assetId: string;
  resource?: string;
  legend?: { value: number; label: string; color: string }[];
  band: number;
  camera?: Camera | null;
  onCamera: (camera: Camera) => void;
  visible: boolean;
  opacity: number;
  onDisplay: (change: {
    visible?: boolean;
    opacity?: number;
    legend_visible?: boolean;
  }) => void;
};
export default function AssetMap(props: AssetMapProps) {
  return (
    <MapBoundary>
      <AssetMapContent {...props} />
    </MapBoundary>
  );
}
function AssetMapContent({
  legendVisible = false,
  layerTitle = "当前图层",
  chrome,
  inspectionResource,
  overlayLayers,
  controls,
  assetId,
  resource: selectedResource,
  legend,
  band,
  camera,
  onCamera,
  visible,
  opacity,
  onDisplay,
}: AssetMapProps) {
  const sharedPanel = useResearchPanel();
  const sharedPanelRef = useRef(sharedPanel);
  useEffect(() => {
    sharedPanelRef.current = sharedPanel;
  }, [sharedPanel]);
  const opacityId = useId();
  const picked = useRef(chrome?.onInspect);
  useEffect(() => {
    picked.current = chrome?.onInspect;
  }, [chrome?.onInspect]);
  const resource = selectedResource ?? `/assets/${assetId}`;
  const view = useQuery({
    queryKey: ["asset-view", resource, band],
    queryFn: () => api(`${resource}/view?band=${band}`, viewSchema),
  });
  const activeResource = inspectionResource ?? resource;
  const displayLayersRef = useRef(overlayLayers);
  useEffect(() => {
    displayLayersRef.current = overlayLayers;
  }, [overlayLayers]);
  const activeResourceRef = useRef(activeResource);
  useEffect(() => {
    activeResourceRef.current = activeResource;
  }, [activeResource]);
  const selectedView = useQuery({
    queryKey: ["asset-view", activeResource, band],
    queryFn: () => api(`${activeResource}/view?band=${band}`, viewSchema),
  });
  const container = useRef<HTMLDivElement>(null),
    mapRef = useRef<Map | null>(null);
  const initialCamera = useRef(camera),
    cameraCallback = useRef(onCamera);
  useEffect(() => {
    cameraCallback.current = onCamera;
  }, [onCamera]);
  const [result, setResult] = useState<
    (z.infer<typeof inspectSchema> & { resource: string }) | null
  >(null);
  const [displayError, setDisplayError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null),
    [loaded, setLoaded] = useState(false),
    [offline, setOffline] = useState(false);
  const displaySettings = useRef({ visible, opacity });
  useEffect(() => {
    displaySettings.current = { visible, opacity };
  }, [visible, opacity]);
  const mapInfo = view.data;
  const info = selectedView.data;
  const categories = legend?.length
    ? legend
    : info?.palette
      ? Object.entries(info.palette).map(([value, color]) => ({
          value: Number(value),
          label: `类别 ${value}`,
          color: `rgba(${color[0]},${color[1]},${color[2]},${(color[3] ?? 255) / 255})`,
        }))
      : undefined;
  useEffect(() => {
    if (!container.current || !mapInfo?.bounds) return;
    const base = baseMapStyle(),
      saved = initialCamera.current;
    const map = new Map({
      container: container.current,
      style: {
        ...base,
        sources: {
          ...base.sources,
          data: {
            type: "raster",
            tiles: [
              `${location.origin}/api${resource}/tiles/{z}/{x}/{y}.png?band=${band}`,
            ],
            tileSize: 256,
            bounds: mapInfo.bounds,
            minzoom: 0,
            maxzoom: 22,
          },
        },
        layers: [
          ...base.layers,
          {
            id: "actual-data",
            type: "raster",
            source: "data",
            paint: {
              "raster-opacity": displaySettings.current.visible
                ? displaySettings.current.opacity
                : 0,
              "raster-resampling": "nearest",
              "raster-fade-duration": 0,
            },
          },
        ],
      },
      ...(saved
        ? {
            center: [saved.longitude, saved.latitude] as [number, number],
            zoom: saved.zoom,
          }
        : { bounds: mapInfo.bounds, fitBoundsOptions: { padding: 32 } }),
    });
    mapRef.current = map;
    map.addControl(new NavigationControl(), "top-right");
    map.addControl(new ScaleControl(), "bottom-left");
    let alive = true,
      request = 0;
    let marker: Marker | undefined;
    // Readiness concerns our data source; an offline basemap must not hold it open.
    map.on("render", () => {
      const ids = displayLayersRef.current
        ?.filter((layer) => layer.visible && layer.opacity > 0)
        .map((layer) => `display-${layer.id}`) ?? ["data"];
      setLoaded(
        ids.length > 0 &&
          ids.every((id) => !!map.getSource(id) && map.isSourceLoaded(id)),
      );
    });
    map.on("error", (event) => {
      if ("sourceId" in event && event.sourceId === "basemap") setOffline(true);
      else setDisplayError(event.error);
    });
    map.on("click", (event) => {
      const sequence = ++request;
      marker?.remove();
      marker = new Marker({ color: "#d74c32" })
        .setLngLat(event.lngLat)
        .addTo(map);
      setResult(null);
      setError(null);
      const inspection = activeResourceRef.current;
      void api(`${inspection}/inspect`, inspectSchema, {
        method: "POST",
        body: JSON.stringify({
          longitude: event.lngLat.lng,
          latitude: event.lngLat.lat,
          band,
        }),
      })
        .then((data) => {
          if (
            alive &&
            sequence === request &&
            inspection === activeResourceRef.current
          ) {
            setResult({ ...data, resource: inspection });
            sharedPanelRef.current?.open({ kind: "pixel", owner: inspection });
            picked.current?.({
              longitude: event.lngLat.lng,
              latitude: event.lngLat.lat,
              band,
            });
          }
        })
        .catch((e) => {
          if (
            alive &&
            sequence === request &&
            inspection === activeResourceRef.current
          )
            setError(e);
        });
    });
    map.on("moveend", (event) => {
      if (event.originalEvent) {
        const center = map.getCenter();
        cameraCallback.current({
          longitude: center.lng,
          latitude: center.lat,
          zoom: map.getZoom(),
        });
      }
    });
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);
    return () => {
      alive = false;
      request++;
      resize.disconnect();
      marker?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, [assetId, resource, band, mapInfo]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const applyDisplay = () => {
      if (!map.getLayer("actual-data")) return;
      if (!overlayLayers) {
        map.setLayoutProperty("actual-data", "visibility", "visible");
        map.setPaintProperty(
          "actual-data",
          "raster-opacity",
          visible ? opacity : 0,
        );
        return;
      }
      map.setLayoutProperty("actual-data", "visibility", "none");
      const ids = new Set(overlayLayers.map((layer) => `display-${layer.id}`));
      for (const layer of map.getStyle().layers) {
        if (layer.id.startsWith("display-") && !ids.has(layer.id)) {
          map.removeLayer(layer.id);
          map.removeSource(layer.id);
        }
      }
      for (const layer of [...overlayLayers].reverse()) {
        const id = `display-${layer.id}`;
        if (!map.getSource(id))
          map.addSource(id, {
            type: "raster",
            tiles: [
              `${location.origin}/api${layer.resource}/tiles/{z}/{x}/{y}.png?band=${layer.band}`,
            ],
            tileSize: 256,
            bounds: mapInfo?.bounds ?? undefined,
            minzoom: 0,
            maxzoom: 22,
          });
        if (!map.getLayer(id))
          map.addLayer({
            id,
            type: "raster",
            source: id,
            paint: {
              "raster-resampling": "nearest",
              "raster-fade-duration": 0,
            },
          });
        map.setLayoutProperty(
          id,
          "visibility",
          layer.visible ? "visible" : "none",
        );
        map.setPaintProperty(id, "raster-opacity", layer.opacity);
        map.moveLayer(id);
      }
    };
    // isStyleLoaded also waits for raster tiles. After the first load event it
    // can become false again, so waiting for another load would lose updates.
    if (map.getLayer("actual-data")) applyDisplay();
    else map.once("styledata", applyDisplay);
    return () => {
      map.off("styledata", applyDisplay);
    };
  }, [mapInfo, overlayLayers, visible, opacity]);
  const locate = useCallback(() => {
    if (!info?.bounds) return;
    mapRef.current?.fitBounds(info.bounds, { padding: 32, duration: 0 });
    const center = mapRef.current?.getCenter();
    cameraCallback.current({
      longitude: center?.lng ?? (info.bounds[0] + info.bounds[2]) / 2,
      latitude: center?.lat ?? (info.bounds[1] + info.bounds[3]) / 2,
      zoom: mapRef.current?.getZoom() ?? 5,
    });
  }, [info]);
  const retry = useCallback(() => {
    setDisplayError(null);
    setLoaded(false);
    void selectedView.refetch();
    void view.refetch();
    const map = mapRef.current;
    const ids = overlayLayers
      ?.filter((layer) => layer.visible)
      .map((layer) => `display-${layer.id}`) ?? ["data"];
    for (const id of ids) {
      const source = map?.getSource<RasterTileSource>(id);
      if (source) source.setTiles([...source.tiles]);
    }
  }, [selectedView, view, overlayLayers]);
  useImperativeHandle(controls, () => ({ locate, retry }), [locate, retry]);
  const layerError = displayError ?? view.error ?? selectedView.error;
  const displayStatus: MapDisplayStatus["state"] = layerError
    ? "error"
    : !mapInfo || !info
      ? "loading"
      : !mapInfo.bounds
        ? "unlocated"
        : !visible
          ? "hidden"
          : loaded
            ? "ready"
            : "loading";
  const displayMessage =
    displayStatus === "error"
      ? "图层显示失败，请重试"
      : displayStatus === "loading"
        ? "正在加载图层"
        : displayStatus === "hidden"
          ? "活动图层已隐藏"
          : displayStatus === "unlocated"
            ? "仅显示原始图像，无可靠地理定位"
            : "当前显示图层已就绪";
  const onStatus = chrome?.onStatus;
  useEffect(() => {
    onStatus?.({ state: displayStatus, message: displayMessage, offline });
  }, [onStatus, displayStatus, displayMessage, offline]);

  const detailContent = info ? (
    <aside
      className="asset-view-details"
      hidden={!sharedPanel && chrome ? !chrome.detailsOpen : false}
      aria-label="图层属性与点查"
    >
      {result && result.resource === activeResource ? (
        <section className="pixel-inspector" aria-label="点查结果">
          <h3>原生像元点查</h3>
          <p>源像元（非显示采样）</p>
          <dl>
            <dt>行 / 列（从 0 计）</dt>
            <dd>
              {result.row} / {result.column}
            </dd>
            <dt>存储值</dt>
            <dd>{result.stored_value ?? "—"}</dd>
            <dt>换算后值</dt>
            <dd>
              {result.value ?? "—"}{" "}
              {result.unit === "1"
                ? "（无量纲）"
                : (result.unit ?? "（单位未声明）")}
            </dd>
            <dt>比例 / 偏移</dt>
            <dd>
              {result.scale} / {result.offset}
            </dd>
            <dt>有效状态</dt>
            <dd>
              {result.status === "outside"
                ? "原件覆盖范围外"
                : result.valid
                  ? "有效"
                  : "NoData / 掩膜无效"}
            </dd>
            <dt>来源</dt>
            <dd>
              {selectedResource ? "成果版本" : "资产版本"}{" "}
              {result.asset_revision} · 波段 {result.band}
              <br />
              <code>{result.sha256}</code>
            </dd>
          </dl>
        </section>
      ) : null}

      {chrome?.details}
      <details open={!chrome}>
        <summary>图层技术信息</summary>

        <h3>图层属性</h3>
        <MapLegend
          title={layerTitle}
          minimum={info.minimum}
          maximum={info.maximum}
          unit={info.unit}
          categories={categories}
        />
        <p className="muted">
          固定显示样本：{info.sample_valid_pixels.toLocaleString()} /{" "}
          {info.sample_pixels.toLocaleString()} 有效；非全域统计。原件{" "}
          {info.width.toLocaleString()} × {info.height.toLocaleString()}{" "}
          像元。点击地图读取源像元；色带与地图视口不改变分析输入。
        </p>
      </details>
    </aside>
  ) : null;
  if (view.isPending) return <p role="status">正在加载资料图层…</p>;
  return (
    <div className="asset-view" data-workbench={!!chrome}>
      <ErrorNotice error={layerError ?? error} />
      {!chrome && displayStatus === "error" ? (
        <button type="button" onClick={retry}>
          重试显示
        </button>
      ) : null}
      {info && sharedPanel?.host
        ? createPortal(
            <div
              hidden={
                sharedPanel.active?.kind !== "style" ||
                sharedPanel.active.owner !== activeResource
              }
            >
              <MapLegend
                title={layerTitle}
                minimum={info.minimum}
                maximum={info.maximum}
                unit={info.unit}
                categories={categories}
              />
              <p>
                固定显示样本：{info.sample_valid_pixels} / {info.sample_pixels}{" "}
                有效；原件 {info.width} × {info.height}{" "}
                像元。完整运行与全域统计见详情。
              </p>
            </div>,
            sharedPanel.host,
          )
        : null}
      {!chrome && sharedPanel?.host
        ? createPortal(
            <div
              hidden={
                sharedPanel.active?.kind !== "style" ||
                sharedPanel.active.owner !== activeResource
              }
            >
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={legendVisible}
                  onChange={(event) =>
                    onDisplay({ legend_visible: event.target.checked })
                  }
                />
                显示地图图例
              </label>
              <label htmlFor={opacityId}>不透明度</label>
              <input
                id={opacityId}
                type="range"
                min="0"
                max="1"
                step=".05"
                value={opacity}
                onChange={(event) =>
                  onDisplay({ opacity: Number(event.target.value) })
                }
              />
              <label>
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={(event) =>
                    onDisplay({ visible: event.target.checked })
                  }
                />
                显示当前资料
              </label>
            </div>,
            sharedPanel.host,
          )
        : null}
      {mapInfo ? (
        <>
          {chrome?.toolbar}
          <div
            className={chrome ? "result-map-stage" : "asset-view-stage"}
            data-details={!sharedPanel && chrome?.detailsOpen}
          >
            <div className="asset-view-map">
              {!chrome && sharedPanel ? (
                <div className="view-tools">
                  <span
                    role="status"
                    className="result-layer-status"
                    data-state={displayStatus}
                    aria-label={
                      displayStatus === "ready" ? "图层就绪" : displayMessage
                    }
                  >
                    {displayStatus === "ready" ? "✓" : displayMessage}
                  </span>
                  <button type="button" className="secondary" onClick={locate}>
                    定位本层
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={(event) =>
                      sharedPanel.open(
                        { kind: "style", owner: resource },
                        event.currentTarget,
                      )
                    }
                  >
                    样式
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={(event) =>
                      sharedPanel.open(
                        { kind: "details", owner: resource },
                        event.currentTarget,
                      )
                    }
                  >
                    详情
                  </button>
                </div>
              ) : !chrome ? (
                <div className="view-tools">
                  <span
                    role="status"
                    className="result-layer-status"
                    data-state={displayStatus}
                    aria-label={
                      displayStatus === "ready" ? "图层就绪" : displayMessage
                    }
                  >
                    {displayStatus === "ready" ? "✓" : displayMessage}
                  </span>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={legendVisible}
                      onChange={(event) =>
                        onDisplay({ legend_visible: event.target.checked })
                      }
                    />
                    显示地图图例
                  </label>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={visible}
                      onChange={(e) => onDisplay({ visible: e.target.checked })}
                    />
                    显示数据层
                  </label>
                  <label htmlFor={opacityId}>
                    不透明度
                    <input
                      id={opacityId}
                      type="range"
                      min="0"
                      max="1"
                      step=".05"
                      value={opacity}
                      onChange={(e) =>
                        onDisplay({ opacity: Number(e.target.value) })
                      }
                    />
                  </label>
                  {mapInfo.bounds ? (
                    <button
                      type="button"
                      className="secondary"
                      onClick={locate}
                    >
                      定位本层
                    </button>
                  ) : null}
                </div>
              ) : null}
              {mapInfo.bounds ? (
                <div
                  ref={container}
                  className="asset-map-canvas"
                  role="region"
                  aria-label="资料地图"
                />
              ) : (
                <>
                  <p className="warning">{mapInfo.issues.join("；")}</p>
                  <img
                    className="native-image"
                    src={`/api${resource}/view.png?band=${band}`}
                    alt="无地理定位的原始像元预览"
                  />
                </>
              )}
              {legendVisible && visible && info ? (
                <MapLegend
                  compact
                  title={layerTitle}
                  minimum={info.minimum}
                  maximum={info.maximum}
                  unit={info.unit}
                  categories={categories}
                />
              ) : null}
            </div>
            {sharedPanel?.host
              ? createPortal(
                  <div
                    hidden={
                      !sharedPanel.active ||
                      sharedPanel.active.kind === "step" ||
                      sharedPanel.active.kind === "style" ||
                      sharedPanel.active.owner !== activeResource
                    }
                  >
                    {detailContent}
                  </div>,
                  sharedPanel.host,
                )
              : detailContent}
          </div>
        </>
      ) : null}
    </div>
  );
}
