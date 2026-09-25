import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError } from "./api";
export const displayStateSchema = z.object({
  vector_present:z.boolean().optional(),
  selected_feature_id:z.string().nullable().optional(),
  legend_visible: z.boolean().optional(),
  artifact_id: z.string().nullable().optional(),
  layers: z
    .array(
      z.object({
        artifact_id: z.string(),
        visible: z.boolean(),
        opacity: z.number(),
      }),
    )
    .optional(),
  asset_id: z.string().nullable(),
  band: z.number(),
  camera: z
    .object({ longitude: z.number(), latitude: z.number(), zoom: z.number() })
    .nullable(),
  visible: z.boolean().default(true),
  opacity: z.number().default(0.9),
});
const responseSchema = z.object({
  revision: z.number(),
  state: displayStateSchema.nullable(),
});
export type DisplayState = z.infer<typeof displayStateSchema>;
export const initialDisplay = (id: string): DisplayState => ({
  asset_id: id,
  band: 1,
  camera: null,
  visible: true,
  opacity: 0.9,
});
export function useViewState(resource: string) {
  const cache = useQueryClient();
  const [local, setLocal] = useState<DisplayState | null>(null);
  const [saving, setSaving] = useState(false),
    [error, setError] = useState<unknown>(null);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const failure = useRef<unknown>(null);
  const saved = useQuery({
    queryKey: ["personal-view", resource],
    queryFn: () => api(resource, responseSchema),
  });
  const save = useCallback(
    (state: DisplayState) => {
      setLocal(state);
      setSaving(true);
      const action = queue.current.then(async () => {
        if (failure.current) throw failure.current;
        const key = ["personal-view", resource];
        const current = cache.getQueryData<z.infer<typeof responseSchema>>(key);
        if (!current) throw new Error("个人视图尚未读取，请重试");
        try {
          const result = await api(resource, responseSchema, {
            method: "PUT",
            body: JSON.stringify({
              expected_revision: current.revision,
              state,
            }),
          });
          cache.setQueryData(key, result);
        } catch (problem) {
          // Recover an uncertain transport result; never overwrite a real conflict.
          if (!(problem instanceof APIError)) {
            const received = await api(resource, responseSchema).catch(
              () => null,
            );
            if (
              received?.revision === current.revision + 1 &&
              JSON.stringify(received.state) ===
                JSON.stringify(displayStateSchema.parse(state))
            ) {
              cache.setQueryData(key, received);
              return;
            }
          }
          throw problem;
        }
      });
      const settled = action.catch((problem) => {
        failure.current = problem;
        setError(problem);
      });
      queue.current = settled;
      void settled.then(() => {
        if (queue.current === settled) setSaving(false);
      });
      return action;
    },
    [resource, cache],
  );
  const restore = useCallback(async () => {
    await queue.current;
    try {
      const received = await api(resource, responseSchema);
      cache.setQueryData(["personal-view", resource], received);
      failure.current = null;
      setError(null);
      setLocal(null);
    } catch (problem) {
      setError(problem);
      throw problem;
    }
  }, [resource, cache]);
  return {
    active: local ?? saved.data?.state,
    ready: !!saved.data,
    saving,
    error: error ?? saved.error,
    save,
    restore,
  };
}
