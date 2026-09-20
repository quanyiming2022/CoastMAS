import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeographicCollection } from "./result-data";
import { geometryPositions } from "./geography";
import { ErrorNotice } from "./components";
export default function GeoMap({
  data,
  label = "分析结果地图",
}: {
  data: GeographicCollection;
  label?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    let active = true;
    let map: LibreMap | undefined;
    let resize: ResizeObserver | undefined;
    void import("maplibre-gl")
      .then(
        ({
          Map,
          LngLatBounds,
          NavigationControl,
          ScaleControl,
          setWorkerUrl,
        }) => {
          if (!active || !container.current) return;
          try {
            setWorkerUrl(workerUrl);
            const bounds = new LngLatBounds();
            for (const feature of data.features)
              for (const point of geometryPositions(feature.geometry))
                bounds.extend(point);
            map = new Map({
              container: container.current,
              style: {
                version: 8,
                sources: { result: { type: "geojson", data } },
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
                    paint: { "fill-color": "#24a5a1", "fill-opacity": 0.45 },
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
                    paint: { "circle-radius": 6, "circle-color": "#13666b" },
                  },
                ],
              },
              attributionControl: false,
              renderWorldCopies: false,
            });
            map.addControl(new NavigationControl(), "top-right");
            map.addControl(new ScaleControl({ unit: "metric" }));
            if (!bounds.isEmpty())
              map.fitBounds(bounds, { padding: 45, duration: 0, maxZoom: 17 });
            map.on("load", () => {
              if (container.current) container.current.dataset.loaded = "true";
            });
            map.on("error", () => {
              if (active)
                setError(
                  new Error("地图渲染失败，请保留结果并检查浏览器图形支持。"),
                );
            });
            resize = new ResizeObserver(() => map?.resize());
            resize.observe(container.current);
          } catch (failure) {
            if (active)
              setError(
                failure instanceof Error
                  ? failure
                  : new Error("地图初始化失败"),
              );
          }
        },
      )
      .catch(() => {
        if (active) setError(new Error("地图组件加载失败"));
      });
    return () => {
      active = false;
      resize?.disconnect();
      map?.remove();
    };
  }, [data]);
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
