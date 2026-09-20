import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeographicCollection } from "./result-data";
import { geometryPositions } from "./geography";
import { ErrorNotice } from "./components";

function updateData(map: LibreMap, data: GeographicCollection, fit: boolean) {
  const source = map.getSource<GeoJSONSource>("result");
  if (!source) return;
  source.setData(data);
  const focus = data.features.filter(
    (feature) => feature.properties?.layer_kind === "aoi",
  );
  const coordinates = (focus.length ? focus : data.features).flatMap(
    (feature) => geometryPositions(feature.geometry),
  );
  if (fit && coordinates.length) {
    let west = Infinity,
      east = -Infinity,
      south = Infinity,
      north = -Infinity;
    for (const [longitude, latitude] of coordinates) {
      west = Math.min(west, longitude);
      east = Math.max(east, longitude);
      south = Math.min(south, latitude);
      north = Math.max(north, latitude);
    }
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      { padding: 45, duration: 0, maxZoom: 17 },
    );
  }
}
export default function GeoMap({
  data,
  label = "分析结果地图",
  onMapClick,
  fitData = true,
}: {
  data: GeographicCollection;
  label?: string;
  onMapClick?: (point: [number, number]) => void;
  fitData?: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LibreMap | null>(null);
  const latest = useRef({ data, fitData, onMapClick });
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    latest.current = { data, fitData, onMapClick };
    const map = mapRef.current;
    if (map?.getSource("result")) {
      if (container.current) container.current.dataset.loaded = "false";
      updateData(map, data, fitData);
    }
  }, [data, fitData, onMapClick]);
  useEffect(() => {
    let active = true;
    let map: LibreMap | undefined;
    let resize: ResizeObserver | undefined;
    const element = container.current;
    if (element) element.dataset.loaded = "false";
    void import("maplibre-gl")
      .then(({ Map, NavigationControl, ScaleControl, setWorkerUrl }) => {
        if (!active || !element) return;
        try {
          setWorkerUrl(workerUrl);
          map = new Map({
            container: element,
            style: {
              version: 8,
              sources: {
                result: { type: "geojson", data: latest.current.data },
              },
              layers: [
                {
                  id: "background",
                  type: "background",
                  paint: { "background-color": "#eaf2f1" },
                },
                {
                  id: "result-fill",
                  filter: ["==", ["geometry-type"], "Polygon"],
                  type: "fill",
                  source: "result",
                  paint: {
                    "fill-color": [
                      "match",
                      ["get", "layer_kind"],
                      "aoi",
                      "#e79d45",
                      "coverage",
                      "#3779b8",
                      "#24a5a1",
                    ],
                    "fill-opacity": 0.3,
                  },
                },
                {
                  id: "result-outline",
                  filter: ["!=", ["geometry-type"], "Point"],
                  type: "line",
                  source: "result",
                  paint: { "line-color": "#13666b", "line-width": 2 },
                },
                {
                  id: "entity-points",
                  type: "circle",
                  source: "result",
                  filter: ["==", ["geometry-type"], "Point"],
                  paint: { "circle-radius": 6, "circle-color": "#b85034" },
                },
              ],
            },
            attributionControl: false,
            renderWorldCopies: false,
          });
          mapRef.current = map;
          map.addControl(new NavigationControl(), "top-right");
          map.addControl(new ScaleControl({ unit: "metric" }));
          map.on("load", () => {
            if (map) updateData(map, latest.current.data, true);
          });
          map.on("idle", () => {
            if (active) element.dataset.loaded = "true";
          });
          map.on("click", (event) =>
            latest.current.onMapClick?.([event.lngLat.lng, event.lngLat.lat]),
          );
          map.on("error", () => {
            if (active) {
              element.dataset.loaded = "false";
              setError(
                new Error("地图渲染失败，请保留数据并检查浏览器图形支持。"),
              );
            }
          });
          resize = new ResizeObserver(() => map?.resize());
          resize.observe(element);
        } catch (failure) {
          if (active)
            setError(
              failure instanceof Error ? failure : new Error("地图初始化失败"),
            );
        }
      })
      .catch(() => {
        if (active) setError(new Error("地图组件加载失败"));
      });
    return () => {
      active = false;
      resize?.disconnect();
      map?.remove();
      mapRef.current = null;
    };
  }, []);
  return (
    <>
      <ErrorNotice error={error} />
      <div ref={container} className="geographic-map" aria-label={label} />
      <p className="muted">
        {label} · WGS 84 经纬度 · 可缩放和平移；未加载外部底图。
      </p>
    </>
  );
}
