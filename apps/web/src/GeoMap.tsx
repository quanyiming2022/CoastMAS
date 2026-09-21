import { useEffect, useRef, useState } from "react";
import type { Map as LibreMap, GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { GeographicCollection } from "./result-data";
import { geometryPositions } from "./geography";
import { ErrorNotice } from "./components";
import { basemapLabels, basemapSource, type Basemap } from "./basemaps";

import { imageCoordinates, type ImageOverlay } from "./imagery";

const noImages: ImageOverlay[] = [];
const layerLabels = {
  "result-fill": "面图层",
  "result-outline": "边界与线图层",
  "entity-points": "点图层",
};
type LayerVisibility = Record<keyof typeof layerLabels, boolean>;
function applyVisibility(map: LibreMap, visibility: LayerVisibility) {
  for (const [id, shown] of Object.entries(visibility)) {
    if (map.getLayer(id))
      map.setLayoutProperty(id, "visibility", shown ? "visible" : "none");
  }
}

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
  onFeatureClick,
  fitData = true,
  images = noImages,
}: {
  data: GeographicCollection;
  images?: ImageOverlay[];
  label?: string;
  onMapClick?: (point: [number, number]) => void;
  fitData?: boolean;
  onFeatureClick?: (properties: Record<string, unknown>) => void;
}) {
  const [visibility, setVisibility] = useState<LayerVisibility>({
    "result-fill": true,
    "result-outline": true,
    "entity-points": true,
  });
  const [selectedImage, setSelectedImage] = useState("");
  const [imageShown, setImageShown] = useState(true);
  const [imageOpacity, setImageOpacity] = useState(0.95);
  const overlay =
    images.find((item) => item.url === selectedImage) ?? images[0];
  const latestImage = useRef({ overlay, imageShown, imageOpacity });
  const [basemap, setBasemap] = useState<Basemap>("none");
  const [imageryDate, setImageryDate] = useState("2024-06-01");
  const [basemapError, setBasemapError] = useState<Error | null>(null);
  const latestBasemap = useRef({ basemap, imageryDate });
  const latestVisibility = useRef(visibility);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<LibreMap | null>(null);
  const latest = useRef({ data, fitData, onMapClick, onFeatureClick });
  const [error, setError] = useState<Error | null>(null);
  useEffect(() => {
    latestImage.current = { overlay, imageShown, imageOpacity };
    const map = mapRef.current;
    if (map?.getSource("result")) applyImage(map, latestImage.current);
  }, [overlay, imageShown, imageOpacity]);
  function changeBasemap(next: Basemap, date: string) {
    try {
      basemapSource(next, date);
      const map = mapRef.current;
      if (map?.getSource("result")) applyBasemap(map, next, date);
      latestBasemap.current = { basemap: next, imageryDate: date };
      setBasemap(next);
      setImageryDate(date);
      setBasemapError(null);
    } catch (failure) {
      setBasemapError(
        failure instanceof Error ? failure : new Error("底图加载失败"),
      );
    }
  }
  useEffect(() => {
    latestVisibility.current = visibility;
    const map = mapRef.current;
    if (map?.isStyleLoaded()) {
      if (container.current) container.current.dataset.loaded = "false";
      applyVisibility(map, visibility);
    }
  }, [visibility]);
  useEffect(() => {
    latest.current = { data, fitData, onMapClick, onFeatureClick };
    const map = mapRef.current;
    if (map?.getSource("result")) {
      if (container.current) container.current.dataset.loaded = "false";
      updateData(map, data, fitData);
    }
  }, [data, fitData, onMapClick, onFeatureClick]);
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
                      "case",
                      ["==", ["get", "selected"], true],
                      "#e07932",
                      [
                        "match",
                        ["get", "layer_kind"],
                        "aoi",
                        "#e79d45",
                        "coverage",
                        "#3779b8",
                        "#24a5a1",
                      ],
                    ],
                    "fill-opacity": [
                      "case",
                      ["==", ["get", "layer_kind"], "raster_boundary"],
                      0,
                      0.3,
                    ],
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
            attributionControl: { compact: false },
            renderWorldCopies: false,
          });
          mapRef.current = map;
          map.addControl(new NavigationControl(), "top-right");
          map.addControl(new ScaleControl({ unit: "metric" }));
          map.on("load", () => {
            if (map) {
              updateData(map, latest.current.data, true);
              applyVisibility(map, latestVisibility.current);
              applyImage(map, latestImage.current);
              applyBasemap(
                map,
                latestBasemap.current.basemap,
                latestBasemap.current.imageryDate,
              );
            }
          });
          map.on("idle", () => {
            if (active) element.dataset.loaded = "true";
          });
          map.on("click", (event) => {
            latest.current.onMapClick?.([event.lngLat.lng, event.lngLat.lat]);
            const feature = map?.queryRenderedFeatures(event.point, {
              layers: ["result-fill", "result-outline", "entity-points"],
            })[0];
            if (feature?.properties)
              latest.current.onFeatureClick?.(feature.properties);
          });
          map.on("error", (event) => {
            if ("sourceId" in event && event.sourceId === "internet-basemap") {
              if (active)
                setBasemapError(
                  new Error(
                    "联网底图未能加载，请检查网络或切换底图；本地场景图层仍可使用。",
                  ),
                );
              return;
            }
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
      <ErrorNotice error={basemapError} />
      <div className="toolbar">
        <label>
          地图底图
          <select
            value={basemap}
            onChange={(event) =>
              changeBasemap(event.target.value as Basemap, imageryDate)
            }
          >
            {Object.entries(basemapLabels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {basemap === "nasa" ? (
          <label>
            底图影像日期
            <input
              type="date"
              value={imageryDate}
              onChange={(event) => changeBasemap(basemap, event.target.value)}
            />
          </label>
        ) : null}
      </div>
      {basemap === "nasa" ? (
        <p className="muted">
          真实 MODIS 真彩色浏览影像，标称 250
          m；放大不增加实际分辨率。日期和云覆盖会影响可见内容，不能替代分析数据。
        </p>
      ) : null}
      {overlay ? (
        <fieldset className="toolbar">
          <legend>场景影像</legend>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={imageShown}
              onChange={(event) => setImageShown(event.target.checked)}
            />
            显示真实影像
          </label>
          <label>
            影像与采集时间
            <select
              value={overlay.url}
              onChange={(event) => setSelectedImage(event.target.value)}
            >
              {images.map((item) => (
                <option key={item.url} value={item.url}>
                  {item.label} · {item.acquired_at}
                </option>
              ))}
            </select>
          </label>
          <label>
            影像透明度
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={imageOpacity}
              onChange={(event) => setImageOpacity(Number(event.target.value))}
            />
          </label>
          <span>
            {overlay.attribution} · 影像仅供显示，分析使用原始数据与质量掩膜
          </span>
        </fieldset>
      ) : null}
      <fieldset className="toolbar">
        <legend>{label}图层控制</legend>
        {(Object.keys(layerLabels) as (keyof LayerVisibility)[]).map((id) => (
          <label className="checkbox-label" key={id}>
            <input
              type="checkbox"
              checked={visibility[id]}
              onChange={(event) =>
                setVisibility((current) => ({
                  ...current,
                  [id]: event.target.checked,
                }))
              }
            />
            显示{layerLabels[id]}
          </label>
        ))}
      </fieldset>
      <div ref={container} className="geographic-map" aria-label={label} />
      <p className="muted">
        {label} · WGS 84 经纬度 · 可缩放和平移 · {basemapLabels[basemap]}
      </p>
    </>
  );
}

function applyBasemap(map: LibreMap, kind: Basemap, date: string) {
  const source = basemapSource(kind, date);
  if (map.getLayer("internet-basemap")) map.removeLayer("internet-basemap");
  if (map.getSource("internet-basemap")) map.removeSource("internet-basemap");
  if (source) {
    map.addSource("internet-basemap", source);
    map.addLayer(
      { id: "internet-basemap", source: "internet-basemap", type: "raster" },
      map.getLayer("scene-image") ? "scene-image" : "result-fill",
    );
  }
}

function applyImage(
  map: LibreMap,
  {
    overlay,
    imageShown,
    imageOpacity,
  }: {
    overlay: ImageOverlay | undefined;
    imageShown: boolean;
    imageOpacity: number;
  },
) {
  if (map.getLayer("scene-image")) map.removeLayer("scene-image");
  if (map.getSource("scene-image")) map.removeSource("scene-image");
  if (!overlay || !imageShown) return;
  map.addSource("scene-image", {
    type: "image",
    url: overlay.url,
    coordinates: imageCoordinates(overlay.bounds) as [
      [number, number],
      [number, number],
      [number, number],
      [number, number],
    ],
  });
  map.addLayer(
    {
      id: "scene-image",
      source: "scene-image",
      type: "raster",
      paint: { "raster-opacity": imageOpacity, "raster-fade-duration": 0 },
    },
    "result-fill",
  );
}
