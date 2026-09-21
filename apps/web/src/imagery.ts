import { z } from "zod";
export const imageBounds = z
  .tuple([z.number(), z.number(), z.number(), z.number()])
  .refine(
    ([west, south, east, north]) =>
      -180 <= west &&
      west < east &&
      east <= 180 &&
      -90 <= south &&
      south < north &&
      north <= 90,
  );
export const imageDescription = z.object({
  bounds: imageBounds,
  label: z.string(),
  attribution: z.string(),
  acquired_at: z.string(),
});
export type ImageOverlay = z.infer<typeof imageDescription> & { url: string };
export function imageCoordinates([west, south, east, north]: z.infer<
  typeof imageBounds
>): [number, number][] {
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
  ];
}
export const opticalPreview = z.object({
  kind: z.literal("optical_preview"),
  url: z.string().startsWith("data:image/png;base64,"),
  bounds: imageBounds,
  label: z.string(),
  minimum: z.number(),
  maximum: z.number(),
  unit: z.literal("1"),
  nodata: z.literal("transparent"),
  resampling: z.string(),
});
