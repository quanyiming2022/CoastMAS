import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import type { FeatureCollection, Geometry } from "geojson";
import {
  Map,
  NavigationControl,
  ScaleControl,
  LngLatBounds,
  type GeoJSONSource,
  type FilterSpecification,
  type ExpressionSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapBoundary, baseMapStyle } from "./mapBase";
import { ErrorNotice } from "./shared";

export type VectorCamera = {
  longitude: number;
  latitude: number;
  zoom: number;
};
export type VectorControls = { locate: () => void };
export type VectorStatus = { ready: boolean; offline: boolean; error: boolean };
type Props = {
  compact?: boolean;
  camera?: VectorCamera | null;
  onCamera?: (camera: VectorCamera) => void;
  controlsRef?: RefObject<VectorControls | null>;
  onStatus?: (status: VectorStatus) => void;
  visible?: boolean;
  opacity?: number;
  data: FeatureCollection<Geometry>;
  themeProperty?: string;
  selected: string | null;
  onSelect: (id: string) => void;
};
export default function VectorMap(props: Props) {
  return (
    <MapBoundary>
      <Contents {...props} />
    </MapBoundary>
  );
}
function extent(collection: FeatureCollection<Geometry>) {
  const bounds = new LngLatBounds();
  function coordinates(value: unknown) {
    if (!Array.isArray(value)) return;
    if (typeof value[0] === "number" && typeof value[1] === "number") {
      if (Number.isFinite(value[0]) && Number.isFinite(value[1]))
        bounds.extend([
          value[0],
          Math.max(-85.051, Math.min(85.051, value[1])),
        ]);
    } else value.forEach(coordinates);
  }
  function geometry(value: Geometry) {
    if (value.type === "GeometryCollection") value.geometries.forEach(geometry);
    else coordinates(value.coordinates);
  }
  collection.features.forEach((feature) => geometry(feature.geometry));
  return bounds;
}
function Contents({
  data,
  selected,
  onSelect,
  themeProperty,
  compact = false,
  camera,
  onCamera,
  controlsRef,
  onStatus,
  visible = true,
  opacity = 0.9,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const choose = useRef(onSelect);
  const cameraCallback = useRef(onCamera);
  const initialCamera = useRef(camera);
  const currentData = useRef(data);
  const fitted = useRef(!!camera);
  useEffect(() => {
    cameraCallback.current = onCamera;
    currentData.current = data;
  }, [onCamera, data]);
  const [ready, setReady] = useState(false);
  const [painted, setPainted] = useState(false);
  const [online, setOnline] = useState("loading");
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    choose.current = onSelect;
  }, [onSelect]);
  const display = useMemo<FeatureCollection<Geometry>>(() => {
    const features = data.features.slice(0, 5000);
    const chosen = data.features.find(
      (feature) => String(feature.id) === selected,
    );
    if (chosen && !features.includes(chosen))
      features[features.length - 1] = chosen;
    return { type: "FeatureCollection", features };
  }, [data, selected]);
  useEffect(() => {
    if (!container.current) return;
    const map = new Map({
      container: container.current,
      style: baseMapStyle(),
      center: initialCamera.current
        ? [initialCamera.current.longitude, initialCamera.current.latitude]
        : [110, 23],
      zoom: initialCamera.current?.zoom ?? 3,
    });
    mapRef.current = map;
    map.addControl(new NavigationControl(), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    map.on("moveend", () => {
      const c = map.getCenter();
      cameraCallback.current?.({
        longitude: c.lng,
        latitude: c.lat,
        zoom: map.getZoom(),
      });
    });
    if (controlsRef)
      controlsRef.current = {
        locate: () => {
          const b = extent(currentData.current);
          if (!b.isEmpty())
            map.fitBounds(b, {
              padding: 40,
              maxZoom: compact ? 20 : 14,
              duration: 0,
            });
        },
      };
    // Layer creation depends on style readiness, never on online tile completion.
    map.on("style.load", () => {
      map.addSource("entities", {
        type: "geojson",
        promoteId: "_coastmas_preview_identity",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer({
        id: "entity-areas",
        type: "fill",
        source: "entities",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#087f8c", "fill-opacity": 0.25 },
      });
      map.addLayer({
        id: "entity-lines",
        type: "line",
        source: "entities",
        filter: ["!=", ["geometry-type"], "Point"],
        paint: { "line-color": "#087f8c", "line-width": 2 },
      });
      map.addLayer({
        id: "entity-points",
        type: "circle",
        source: "entities",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-color": "#087f8c",
          "circle-radius": 6,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      });
      map.addLayer({
        id: "chosen-line",
        type: "line",
        source: "entities",
        filter: ["==", ["get", "_coastmas_preview_identity"], ""],
        paint: { "line-color": "#b45309", "line-width": 4 },
      });
      map.addLayer({
        id: "chosen-point",
        type: "circle",
        source: "entities",
        filter: [
          "all",
          ["==", ["get", "_coastmas_preview_identity"], ""],
          ["==", ["geometry-type"], "Point"],
        ],
        paint: {
          "circle-color": "#b45309",
          "circle-radius": 9,
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2,
        },
      });
      setReady(true);
    });
    map.on("click", (event) => {
      if (!map.getLayer("entity-points")) return;
      const found = map.queryRenderedFeatures(event.point, {
        layers: ["entity-points", "entity-lines", "entity-areas"],
      })[0];
      const identity = found?.properties?._coastmas_preview_identity;
      if (typeof identity === "string") choose.current(identity);
    });
    map.on("render", () => {
      if (
        map.getLayer("entity-points") &&
        map.queryRenderedFeatures({
          layers: ["entity-points", "entity-lines", "entity-areas"],
        }).length > 0
      )
        setPainted(true);
    });
    map.on("sourcedata", (event) => {
      if (event.sourceId === "basemap" && event.tile?.state === "loaded")
        setOnline("ready");
    });
    map.on("error", (event) => {
      if ("sourceId" in event && event.sourceId === "basemap")
        setOnline("unavailable");
      else setError(event.error);
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      if (controlsRef) controlsRef.current = null;
    };
  }, [controlsRef, compact]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const color: string | ExpressionSpecification =
      themeProperty === "assessment_score"
        ? [
            "interpolate",
            ["linear"],
            ["get", "assessment_score"],
            0,
            "#2c7bb6",
            0.5,
            "#ffffbf",
            1,
            "#d7191c",
          ]
        : themeProperty === "selected"
          ? ["case", ["==", ["get", "selected"], true], "#087f8c", "#aebdc2"]
          : "#087f8c";
    map.setPaintProperty("entity-areas", "fill-color", color);
    map.setPaintProperty(
      "entity-areas",
      "fill-opacity",
      themeProperty ? 0.8 : 0.25,
    );
    map.setPaintProperty("entity-points", "circle-color", color);
  }, [themeProperty, ready]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    // Tile encoders may coerce numeric-looking GeoJSON IDs; promote the exact
    // source string from a display-only property without changing stored data.
    void (map.getSource("entities") as GeoJSONSource)
      .setData({
        ...display,
        features: display.features.map((feature) => ({
          ...feature,
          properties: {
            ...feature.properties,
            _coastmas_preview_identity: String(feature.id),
          },
        })),
      })
      .catch(setError);
    const chosen = display.features.find(
      (feature) => String(feature.id) === selected,
    );
    const bounds = extent(
      chosen ? { type: "FeatureCollection", features: [chosen] } : display,
    );
    if (!bounds.isEmpty() && (!compact || !fitted.current)) {
      map.fitBounds(bounds, {
        padding: 40,
        maxZoom: compact ? 20 : 14,
        duration: 0,
      });
      fitted.current = true;
    }
    const match: FilterSpecification = [
      "==",
      ["get", "_coastmas_preview_identity"],
      selected ?? "",
    ];
    map.setFilter("chosen-line", [
      "all",
      match,
      ["!=", ["geometry-type"], "Point"],
    ]);
    map.setFilter("chosen-point", [
      "all",
      match,
      ["==", ["geometry-type"], "Point"],
    ]);
  }, [display, selected, ready, compact]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    for (const id of [
      "entity-areas",
      "entity-lines",
      "entity-points",
      "chosen-line",
      "chosen-point",
    ])
      map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    map.setPaintProperty("entity-areas", "fill-opacity", opacity);
    map.setPaintProperty("entity-lines", "line-opacity", opacity);
    map.setPaintProperty("entity-points", "circle-opacity", opacity);
  }, [ready, visible, opacity]);
  useEffect(() => {
    onStatus?.({
      ready: painted,
      offline: online === "unavailable",
      error: !!error,
    });
  }, [painted, online, error, onStatus]);
  return (
    <div className={compact ? "map-result compact-vector-map" : "map-result"}>
      <ErrorNotice error={error} />
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label={compact ? "本次矢量成果地图" : "实体成果地图"}
      />
      {!compact && themeProperty === "assessment_score" ? (
        <div className="view-legend" aria-label="评价得分图例">
          <span style={{ background: "#2c7bb6" }}>0</span> —{" "}
          <span style={{ background: "#ffffbf" }}>0.5</span> —{" "}
          <span style={{ background: "#d7191c", color: "white" }}>1</span> ·
          本次实际评价得分
        </div>
      ) : null}
      {!compact ? (
        <>
          <p role="status">
            {online === "ready"
              ? "互联网底图已加载"
              : online === "unavailable"
                ? "互联网底图不可用，仍可查看实际实体层"
                : "正在请求互联网底图…"}
          </p>
          <p role="status">
            {painted ? "实际实体层已绘制" : "正在绘制实际实体层…"}
          </p>
          <p>
            {data.features.length > 5000
              ? `地图显示 ${display.features.length} / ${data.features.length} 个实体的有界预览，包含当前选择；下载保留全部实体。`
              : `地图显示全部 ${display.features.length} 个实际实体。`}{" "}
            {themeProperty
              ? "按本次实际计算值着色，橙色边线或标记为当前选择。"
              : "青色为实体，橙色边线或标记为当前选择。"}
          </p>
        </>
      ) : null}
    </div>
  );
}
