import type { RasterSourceSpecification } from "maplibre-gl";
export type Basemap = "none" | "osm" | "nasa";
export const basemapLabels: Record<Basemap, string> = {
  none: "无底图（离线）",
  osm: "街道底图（OpenStreetMap）",
  nasa: "卫星影像底图（NASA MODIS）",
};
export function basemapSource(
  kind: Basemap,
  date: string,
): RasterSourceSpecification | null {
  if (kind === "none") return null;
  if (kind === "osm")
    return {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
    };
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
    Number.isNaN(Date.parse(date)) ||
    new Date(date).toISOString().slice(0, 10) !== date
  )
    throw new Error("请选择有效的影像日期");
  return {
    type: "raster",
    tiles: [
      `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
    ],
    tileSize: 256,
    maxzoom: 9,
    attribution:
      '<a href="https://www.earthdata.nasa.gov/eosdis/science-system-description/eosdis-standard-products" target="_blank" rel="noopener">NASA EOSDIS GIBS · Terra MODIS</a>',
  };
}
