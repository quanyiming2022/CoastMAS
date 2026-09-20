import { z } from "zod";
const position = z.tuple([
  z.number().min(-180).max(180),
  z.number().min(-90).max(90),
]);
const ring = z
  .array(position)
  .min(4)
  .refine(
    (points) =>
      points[0]?.[0] === points.at(-1)?.[0] &&
      points[0]?.[1] === points.at(-1)?.[1],
    "Polygon ring must be closed",
  );
const polygon = z.object({
  type: z.literal("Polygon"),
  coordinates: z.array(ring).min(1),
});
const multiPolygon = z.object({
  type: z.literal("MultiPolygon"),
  coordinates: z.array(z.array(ring).min(1)).min(1),
});
export const geographicCollection = z.object({
  type: z.literal("FeatureCollection"),
  features: z.array(
    z.object({
      type: z.literal("Feature"),
      id: z.union([z.string(), z.number()]).optional(),
      geometry: z.union([
        polygon,
        multiPolygon,
        z.object({ type: z.literal("Point"), coordinates: position }),
        z.object({
          type: z.literal("MultiPoint"),
          coordinates: z.array(position).min(1),
        }),
        z.object({
          type: z.literal("LineString"),
          coordinates: z.array(position).min(2),
        }),
        z.object({
          type: z.literal("MultiLineString"),
          coordinates: z.array(z.array(position).min(2)).min(1),
        }),
      ]),
      properties: z.record(z.string(), z.unknown()).nullable(),
    }),
  ),
});
export type GeographicCollection = z.infer<typeof geographicCollection>;
export const coastalStatistics = z.object({
  inundated_area_m2: z.number().nonnegative(),
  estimated_affected_population: z.number().nonnegative(),
  unknown_area_m2: z.number().nonnegative(),
  population_assumption: z.literal("uniform within each management unit"),
  method: z.literal("terrain-connectivity screening, not hydrodynamics"),
  units: z.record(
    z.string(),
    z.object({
      inundated_area_m2: z.number().nonnegative(),
      estimated_population: z.number().nonnegative(),
      unknown_area_m2: z.number().nonnegative(),
    }),
  ),
});
