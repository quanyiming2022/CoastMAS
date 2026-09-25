import { useEffect, useRef, useState } from "react";
import { MapBoundary, baseMapStyle } from "./mapBase";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Map, NavigationControl, LngLatBounds } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api } from "./api";
import { ErrorNotice } from "./shared";
const position = z.tuple([z.number(), z.number()]);
const previewSchema = z.object({
  coordinates: z.tuple([position, position, position, position]),
  preview_minimum: z.number(),
  preview_maximum: z.number(),
  sampled_valid_pixels: z.number(),
  scope: z.string(),
  legend: z.array(
    z.object({ value: z.number(), label: z.string(), color: z.string() }),
  ),
  unit: z.string().nullable(),
});
export default function PreviewMap({ resource }: { resource: string }) {
  return (
    <MapBoundary>
      <MapContents resource={resource} />
    </MapBoundary>
  );
}
function MapContents({ resource }: { resource: string }) {
  const container = useRef<HTMLDivElement>(null);
  const [online, setOnline] = useState<"loading" | "ready" | "unavailable">(
    "loading",
  );
  const [mapError, setMapError] = useState<unknown>(null);
  const preview = useQuery({
    queryKey: ["preview", resource],
    queryFn: () => api(resource + "/preview", previewSchema),
  });
  useEffect(() => {
    if (!container.current || !preview.data) return;
    const corners = preview.data.coordinates;
    const bounds = new LngLatBounds();
    corners.forEach((point) => bounds.extend(point));
    const base = baseMapStyle();
    const map = new Map({
      container: container.current,
      bounds,
      fitBoundsOptions: { padding: 32 },
      style: {
        version: 8,
        sources: {
          ...base.sources,
          observations: {
            type: "image",
            url: "/api" + resource + "/preview.png",
            coordinates: corners,
          },
        },
        layers: [
          ...base.layers,
          {
            id: "actual-values",
            type: "raster",
            source: "observations",
            paint: { "raster-opacity": 0.84, "raster-resampling": "nearest" },
          },
        ],
      },
    });
    map.addControl(new NavigationControl(), "top-right");
    map.on("sourcedata", (event) => {
      if (event.sourceId === "basemap" && event.tile?.state === "loaded")
        setOnline("ready");
    });
    map.on("error", (event) => {
      if ("sourceId" in event && event.sourceId === "basemap")
        setOnline("unavailable");
      else setMapError(event.error);
    });
    return () => map.remove();
  }, [preview.data, resource]);
  return (
    <div className="map-result">
      <ErrorNotice error={preview.error ?? mapError} />
      {preview.isPending ? <p role="status">正在加载空间预览…</p> : null}
      <div
        ref={container}
        className="map-canvas"
        role="region"
        aria-label="实际成果地图"
      />
      <p role="status">
        {online === "ready"
          ? "互联网底图已加载"
          : online === "unavailable"
            ? "互联网底图不可用，仍可查看实际数据层"
            : "正在请求互联网底图…"}
      </p>
      {preview.data ? (
        <>
          <p>
            地图为有界显示预览，图中有效采样像元{" "}
            {preview.data.sampled_valid_pixels} 个；预览值范围{" "}
            {preview.data.preview_minimum.toPrecision(6)}—
            {preview.data.preview_maximum.toPrecision(6)}{" "}
            {preview.data.unit ?? "（文件未声明单位）"}
            。完整数据请下载标准成果。
          </p>
          {preview.data.legend.length ? (
            <ul className="map-legend">
              {preview.data.legend.map((item) => (
                <li key={item.value}>
                  <span style={{ backgroundColor: item.color }} />
                  {item.label}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
