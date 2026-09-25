import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema } from "./api";
import { contract } from "./contracts";
import type { ModelSpec } from "./generated/contracts";
import { ErrorNotice, Panel } from "./components";
const revision = revisionSchema.extend({ spec: contract("ModelSpec") });
const availability = z.object({
  available: z.boolean(),
  reason: z.string().nullable(),
  can_approve: z.boolean(),
  can_register: z.boolean(),
  models: z.array(
    z.object({
      method: z.string(),
      name: z.string(),
      license: z.string(),
      image: z.string(),
      id: z.string(),
      registered: z.boolean(),
    }),
  ),
});
export default function ProvidedModels({
  projectId,
  model,
  onSaved,
}: {
  projectId: string;
  model: ModelSpec | null;
  onSaved: (value: z.infer<typeof revision>) => Promise<void>;
}) {
  const cache = useQueryClient();
  const query = useQuery({
    queryKey: ["provided-models", projectId],
    enabled: !model || model.id.startsWith("business:"),
    queryFn: ({ signal }) =>
      request(
        `/models/provided-packages?project_id=${encodeURIComponent(projectId)}`,
        availability,
        { signal },
      ),
  });
  const action = useMutation({
    mutationFn: (method: string | null) =>
      method
        ? request("/models/provided-packages", revision, {
            method: "POST",
            body: { project_id: projectId, method },
          })
        : request(
            `/models/${encodeURIComponent(model!.id)}/approve-provided-runtime`,
            revision,
            { method: "POST", body: { expected_version: model!.version } },
          ),
    onSuccess: async (value) => {
      await cache.invalidateQueries({
        queryKey: ["provided-models", projectId],
      });
      await onSaved(value);
    },
  });
  if (model && !model.id.startsWith("business:")) return null;
  return (
    <Panel title="已提供的真实模型">
      <ErrorNotice error={query.error ?? action.error} />
      <p>
        PPCI用于聚类；pprRFA用于回归，回归必须提供响应变量。技术数值对照通过后仍需管理员批准当前固定运行版本；不自动认定海岸业务结论有效。
      </p>
      {query.isPending ? <p role="status">正在读取运行准备状态…</p> : null}
      {query.data?.available === false ? (
        <p>运行包尚未就绪：{query.data.reason}</p>
      ) : null}
      {!model
        ? query.data?.models.map((item) => (
            <div className="toolbar" key={item.method}>
              <span>
                {item.name} · {item.license}
              </span>
              {item.registered ? (
                <Link to={`/models/${encodeURIComponent(item.id)}/edit`}>
                  打开已登记模型
                </Link>
              ) : (
                <button
                  type="button"
                  disabled={action.isPending || !query.data?.can_register}
                  onClick={() => action.mutate(item.method)}
                >
                  登记{item.name}
                </button>
              )}
            </div>
          ))
        : null}
      {model &&
      model.execution_status !== "EXECUTABLE" &&
      query.data?.available ? (
        query.data.can_approve ? (
          <button
            type="button"
            disabled={action.isPending}
            onClick={() => action.mutate(null)}
          >
            批准此版本运行适配器
          </button>
        ) : (
          <p>已登记，待项目管理员审批运行适配器。</p>
        )
      ) : null}
      {model?.execution_status === "EXECUTABLE" ? (
        <p>运行适配器已审批；输入映射与工作流科学预检仍必须通过。</p>
      ) : null}
    </Panel>
  );
}
