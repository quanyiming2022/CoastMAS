import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "./api";
import { ErrorNotice } from "./shared";
import type { TaskRecord } from "./draft";
const schema = z.object({
  task_id: z.string(),
  revision: z.number(),
  guidance: z.string(),
  requirements: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      status: z.string(),
      alternatives: z.array(z.object({ id: z.string(), label: z.string() })),
    }),
  ),
});
const labels: Record<string, string> = {
  used: "已使用",
  reusable: "可复用",
  can_generate: "可从现有资料生成",
  needs_review: "待核对",
  missing: "需补充",
  not_implemented: "尚未接入",
};
export function InputRequirements({ task }: { task: TaskRecord }) {
  const check = useQuery({
    queryKey: ["input-requirements", task.project_id, task.id, task.revision],
    queryFn: ({ signal }) =>
      api(`/tasks/${task.id}/input-requirements`, schema, { signal }),
  });
  return (
    <section className="import-requirements" aria-label="本研究资料要求">
      <ErrorNotice error={check.error} />
      {check.isPending ? <p>正在核对本次资料要求…</p> : null}
      {check.data ? (
        <>
          <p>{check.data.guidance}</p>
          {check.data.requirements.length ? (
            <details>
              <summary>
                {
                  check.data.requirements.filter((r) => r.status !== "used")
                    .length
                }
                项资料需要核对
              </summary>
              <ul>
                {check.data.requirements.map((r) => (
                  <li key={r.id}>
                    <strong>{r.label}</strong> · {labels[r.status] ?? r.status}
                    <div>
                      {r.alternatives.map((a) => a.label).join("，任选其一")}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
