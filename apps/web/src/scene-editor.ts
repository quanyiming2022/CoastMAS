import { geographicCollection } from "./result-data";
import type { VersionReference } from "./generated/contracts";

export function aoiFromUpload(raw: unknown) {
  const candidate =
    typeof raw === "object" &&
    raw !== null &&
    "type" in raw &&
    raw.type === "Feature" &&
    "geometry" in raw
      ? raw.geometry
      : raw;
  const geometry =
    geographicCollection.shape.features.element.shape.geometry.parse(candidate);
  if (geometry.type !== "Polygon" && geometry.type !== "MultiPolygon")
    throw new Error(
      "AOI 必须是单个 Polygon、MultiPolygon 或包含它们的 Feature",
    );
  return geometry;
}
export function closeDrawing(points: [number, number][]) {
  if (
    points.length < 3 ||
    new Set(points.map((point) => JSON.stringify(point))).size < 3
  )
    throw new Error("至少选择三个不同顶点");
  return aoiFromUpload({
    type: "Polygon",
    coordinates: [[...points, points[0]]],
  });
}
export function toggleReference(
  references: VersionReference[],
  reference: VersionReference,
  selected: boolean,
): VersionReference[] {
  const remaining = references.filter((item) => item.id !== reference.id);
  return selected ? [...remaining, reference] : remaining;
}
