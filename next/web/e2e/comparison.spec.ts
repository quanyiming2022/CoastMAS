import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { evidenceDirectory, evidencePath } from "./evidence";

test("comparison reuses actual immutable CF runs, saves selection and exports converted differences", async ({
  page,
}) => {
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!accessFile) throw new Error("Isolated test account required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  const headers = { "X-CSRF-Token": session.csrf };
  const prefix = "实际CF比较 " + Date.now();
  const jobs: string[] = [];
  // Actual fixture preparation only; not counted as end-user comparison actions.
  // No result rows or scientific answers are inserted into the database.
  for (const unit of ["m", "cm"]) {
    const made = await page.request.post("/api/tasks", {
      headers,
      data: {
        project_id: access.project_id,
        title: prefix + " " + unit,
        purpose: "temporal",
      },
    });
    expect(made.status()).toBe(201);
    const task = await made.json();
    const upload = await page.request.post(
      `/api/projects/${access.project_id}/assets`,
      {
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
      },
    );
    expect(upload.status()).toBe(201);
    const attached = (await upload.json()).task;
    attached.draft.options = {
      ...attached.draft.options,
      start: "2022-02-29",
      end: "2022-03-02",
      output_unit: unit,
    };
    const saved = await page.request.put(`/api/tasks/${task.id}`, {
      headers,
      data: { expected_revision: attached.revision, draft: attached.draft },
    });
    expect(saved.status()).toBe(200);
    const run = await page.request.post(`/api/tasks/${task.id}/execute`, {
      headers,
      data: {
        expected_revision: (await saved.json()).revision,
        idempotency_key: "actual-comparison-input",
      },
    });
    expect(run.status()).toBe(202);
    const id = (await run.json()).id;
    jobs.push(id);
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/jobs/${id}`)).json()).status,
      )
      .toBe("succeeded");
  }
  await page.getByLabel("任务名称", { exact: true }).fill(prefix);
  await page
    .getByRole("combobox", { name: "任务类型", exact: true })
    .selectOption("comparison");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "成果比较", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("radio", { name: new RegExp("^作为基准：" + prefix + " m，") })
    .check();
  await page
    .getByRole("radio", { name: new RegExp("^作为对照：" + prefix + " cm，") })
    .check();
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  const taskURL = page.url();
  await page.reload();
  await expect(
    page.getByRole("radio", {
      name: new RegExp("^作为基准：" + prefix + " m，"),
    }),
  ).toBeChecked();
  await expect(
    page.getByRole("radio", {
      name: new RegExp("^作为对照：" + prefix + " cm，"),
    }),
  ).toBeChecked();
  const requested = page.waitForResponse(
    (r) => r.url().endsWith("/execute") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "核对并比较", exact: true }).click();
  const executed = await requested;
  expect(executed.status()).toBe(202);
  const job = await executed.json();
  await expect(page.getByRole("table", { name: "逐项比较" })).toBeVisible();
  await expect(
    page.getByText("自动单位转换：cm → m（保留转换记录）", { exact: true }),
  ).toBeVisible();
  const row = page
    .getByRole("table", { name: "逐项比较" })
    .getByRole("row")
    .nth(1);
  await expect(row.getByRole("cell")).toHaveText([
    "height",
    "2",
    "2",
    "0",
    "m",
  ]);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const path = await (await download).path();
  if (!path) throw new Error("No actual download");
  const actual = JSON.parse(await readFile(path, "utf8"));
  expect(actual.data.rows).toEqual([
    { id: "height", left: 2, right: 2, difference: 0, unit: "m" },
  ]);
  expect(
    actual.manifest.comparison_inputs.map((i: { job_id: string }) => i.job_id),
  ).toEqual(jobs);
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 1);
    await page.screenshot({
      path: evidencePath(`comparison-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("result-comparison.json"),
    JSON.stringify(
      {
        task_url: taskURL,
        job_id: job.id,
        source_jobs: jobs,
        actual_rows: actual.data.rows,
        scientific_status: "engineering_only",
        measured_input: {
          scope:
            "comparison only; actual CF source runs prepared separately through upload and worker",
          manual_fills: 1,
          selections: 3,
          confirmations: 0,
          duplicate_fills: 0,
          cross_page_trips: 0,
          refresh_recovered: true,
        },
      },
      null,
      2,
    ),
  );
});
