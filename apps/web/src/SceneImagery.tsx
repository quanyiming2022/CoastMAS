import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { request } from "./api";
import { imageDescription, type ImageOverlay } from "./imagery";
import type { VersionReference } from "./generated/contracts";

export function useSceneImagery(
  project: string,
  references: readonly VersionReference[],
) {
  return useQuery({
    queryKey: ["scene-imagery", project, references],
    queryFn: async ({ signal }): Promise<ImageOverlay[]> => {
      const rows = await Promise.all(
        references.map(async (reference) => {
          const prefix = `/data-assets/${encodeURIComponent(reference.id)}`;
          const value = await request(
            `${prefix}/imagery-series?version=${reference.version}`,
            z.array(imageDescription),
            { signal },
          );
          return value.map((item, frame) => ({
            ...item,
            url: `/api/v1${prefix}/image?version=${reference.version}&frame=${frame}`,
          }));
        }),
      );
      const unique = new Map<string, ImageOverlay>();
      for (const row of rows.flat())
        if (row)
          unique.set(
            JSON.stringify([row.label, row.acquired_at, row.bounds]),
            row,
          );
      return [...unique.values()];
    },
  });
}
