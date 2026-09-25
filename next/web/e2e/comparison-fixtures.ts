import { expect, type APIRequestContext } from "@playwright/test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
export async function actualComparison(
  api: APIRequestContext,
  project: string,
  headers: Record<string, string>,
  title: string,
) {
  const jobs: string[] = [];
  for (const unit of ["m", "cm"]) {
    const made = await api.post("/api/tasks", {
      headers,
      data: {
        project_id: project,
        title: title + " " + unit,
        purpose: "temporal",
      },
    });
    expect(made.status()).toBe(201);
    const task = await made.json();
    const uploaded = await api.post(`/api/projects/${project}/assets`, {
      headers,
      multipart: {
        file: {
          name: "temporal-360day.nc",
          mimeType: "application/x-netcdf",
          buffer: await readFile(
            fileURLToPath(
              new URL("./fixtures/temporal-360day.nc", import.meta.url),
            ),
          ),
        },
        task_id: task.id,
        expected_revision: "1",
      },
    });
    expect(uploaded.status()).toBe(201);
    const attached = (await uploaded.json()).task;
    attached.draft.options = {
      ...attached.draft.options,
      start: "2022-02-29",
      end: "2022-03-02",
      output_unit: unit,
    };
    const saved = await api.put(`/api/tasks/${task.id}`, {
      headers,
      data: { expected_revision: attached.revision, draft: attached.draft },
    });
    expect(saved.status()).toBe(200);
    const run = await api.post(`/api/tasks/${task.id}/execute`, {
      headers,
      data: {
        expected_revision: (await saved.json()).revision,
        idempotency_key: "actual-input",
      },
    });
    expect(run.status()).toBe(202);
    const id = (await run.json()).id;
    jobs.push(id);
    await expect
      .poll(
        async () => (await (await api.get(`/api/jobs/${id}`)).json()).status,
      )
      .toBe("succeeded");
  }
  const made = await api.post("/api/tasks", {
    headers,
    data: { project_id: project, title, purpose: "comparison" },
  });
  expect(made.status()).toBe(201);
  const task = await made.json();
  task.draft.options = { left_job_id: jobs[0], right_job_id: jobs[1] };
  const saved = await api.put(`/api/tasks/${task.id}`, {
    headers,
    data: { expected_revision: task.revision, draft: task.draft },
  });
  expect(saved.status()).toBe(200);
  const run = await api.post(`/api/tasks/${task.id}/execute`, {
    headers,
    data: {
      expected_revision: (await saved.json()).revision,
      idempotency_key: "actual-comparison",
    },
  });
  expect(run.status()).toBe(202);
  const job = (await run.json()).id;
  await expect
    .poll(async () => (await (await api.get(`/api/jobs/${job}`)).json()).status)
    .toBe("succeeded");
  return { task: task.id, job };
}
