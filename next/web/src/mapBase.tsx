import { Component, type ReactNode } from "react";
import { setWorkerUrl, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
// MapLibre 6 ships a separate worker; bundle it instead of a missing sibling URL.
setWorkerUrl(workerUrl);
export function baseMapStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution:
          '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#ecf0f1" },
      },
      { id: "basemap", type: "raster", source: "basemap" },
    ],
  };
}
export class MapBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <p role="alert" className="error">
        地图初始化失败：{this.state.error.message}。数据文件仍可下载。
      </p>
    ) : (
      this.props.children
    );
  }
}
