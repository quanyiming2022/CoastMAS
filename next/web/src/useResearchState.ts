import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError } from "./api";
export const researchStateSchema = z.object({
  active_task_id: z.string().nullable(),
  inspected_asset_id: z.string().nullable(),
  viewed_job_id: z.string().nullable(),
  panel: z.enum([
    "research",
    "tasks",
    "data",
    "methods",
    "runs",
    "results",
    "tools",
  ]),
  central_view: z.enum(["map", "configuration", "result"]),
  content_tab: z.enum(["layers", "inputs", "runs"]).optional(),
  dock_heights: z.record(z.string(), z.number().min(120).max(4000)).optional(),
  drawer: z.enum(["closed", "open", "maximized"]),
});
const responseSchema = z.object({
  revision: z.number(),
  state: researchStateSchema.nullable(),
});
export type ResearchState = z.infer<typeof researchStateSchema>;
export const initialResearch: ResearchState = {
  active_task_id: null,
  inspected_asset_id: null,
  viewed_job_id: null,
  panel: "research",
  central_view: "map",
  drawer: "closed",
};
export function useResearchState(resource: string) {
  const cache = useQueryClient();
  const [local, setLocal] = useState<ResearchState | null>(null);
  const [saving, setSaving] = useState(false),
    [error, setError] = useState<unknown>(null);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const failure = useRef<unknown>(null);
  const saved = useQuery({
    queryKey: ["research-state", resource],
    queryFn: () => api(resource, responseSchema),
  });
  const save = useCallback(
    (state: ResearchState) => {
      setLocal(state);
      setSaving(true);
      const action = queue.current.then(async () => {
        if (failure.current) throw failure.current;
        const key = ["research-state", resource];
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
                JSON.stringify(researchStateSchema.parse(state))
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
      cache.setQueryData(["research-state", resource], received);
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
