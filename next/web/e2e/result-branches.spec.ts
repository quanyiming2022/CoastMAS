import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { evidenceDirectory, evidencePath } from "./evidence";
async function hash(path: string) {
  const h = createHash("sha256");
  for await (const chunk of createReadStream(path)) h.update(chunk);
  return h.digest("hex");
}

test("B actual full raster composite, layer groups, original-value inspect and immutable historical switching with A", async ({
  page,
}) => {
  test.setTimeout(540000);
  const file = process.env.COASTMAS_NEXT_CONSTRUCTION_RASTER;
  if (!file || !process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Real raster and isolated credentials required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "数据资源", exact: true }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/session")).json();
  const headers = { "X-CSRF-Token": session.csrf };
  const projectResponse = await page.request.post("/api/projects", {
    headers,
    data: { name: "空间成果分支隔离验收 " + Date.now() },
  });
  expect(projectResponse.status()).toBe(201);
  const project = (await projectResponse.json()).id;
  async function method(title: string, positive: boolean, profile: string) {
    const response = await page.request.post(
      `/api/projects/${project}/templates`,
      {
        headers,
        data: {
          title,
          purpose: "method",
          profiles: [profile],
          basis:
            "明确工程基准，固定距离0—1000000米，单指标权重1；不代表正式生态评价依据。",
          configuration: {
            task: "assessment",
            method: "weighted",
            indicators: [
              {
                concept: "distance",
                unit: "m",
                lower: 0,
                upper: 1000000,
                positive,
                weight: 1,
              },
            ],
          },
        },
      },
    );
    expect(response.status()).toBe(201);
    const m = await response.json();
    expect(
      (
        await page.request.post(`/api/templates/${m.id}/approve`, {
          headers,
          data: { revision: 1 },
        })
      ).ok(),
    ).toBe(true);
    return m;
  }
  const positive = await method("正向工程评价", true, "geotiff"),
    negative = await method("反向工程评价", false, "geotiff");
  await page.goto("/library?project=" + project);
  const upload = page.waitForResponse(
    (r) => r.url().endsWith("/complete") && r.request().method() === "POST",
    { timeout: 120000 },
  );
  await page.getByLabel("导入并查看资料", { exact: true }).setInputFiles(file);
  const asset = (await (await upload).json()).asset;
  expect(asset.size).toBe((await stat(file)).size);
  expect(asset.size).toBeGreaterThan(64 * 1024 ** 2);
  await expect(page.getByRole("status", { name:"图层就绪", exact: true })).toBeVisible(
    { timeout: 90000 },
  );
  expect(
    await (await page.request.get(`/api/projects/${project}/tasks`)).json(),
  ).toHaveLength(0);
  await page.getByRole("button", { name: "新建研究", exact: true }).click();
  await page
    .getByRole("dialog", { name: "新建研究任务" })
    .getByRole("button", { name: "创建并继续" })
    .click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  const taskId = new URL(page.url()).pathname.split("/tasks/")[1]!;
  expect(taskId).toBeTruthy();
  await page.getByRole("link", { name: "数据资源", exact: true }).click();
  await page.getByRole("button", { name: "加入当前任务", exact: true }).click();
  async function apply(title: string) {
    await page.getByRole("link", { name: "方法方案", exact: true }).click();
    const catalog = page.getByRole("region", { name: "方法方案", exact: true });
    await catalog.getByLabel("搜索方法方案", { exact: true }).fill(title);
    await catalog.getByLabel("搜索方法方案", { exact: true }).press("Enter");
    await catalog
      .getByRole("button", { name: "查看方法", exact: true })
      .click();
    await page
      .getByRole("button", { name: "应用到当前任务", exact: true })
      .click();
    await expect(page.getByRole('dialog',{name:'方法版本详情'})).toBeHidden();
  }
  await apply("正向工程评价");
  await page
    .getByLabel("科学含义 raster/band_1", { exact: true })
    .fill("distance");
  await page.getByLabel("单位 raster/band_1", { exact: true }).fill("m");
  await page
    .getByLabel("支撑 raster/band_1", { exact: true })
    .selectOption("grid");
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  const region = page.locator(".research-result");
  const inspector = page.getByRole("complementary", {
    name: "研究共用右侧面板",
  });
  async function styleValue() {
    await region.getByRole("button", { name: "样式", exact: true }).click();
    await expect(
      inspector.getByRole("slider", { name: "不透明度", exact: true }),
    ).toHaveValue("0.6");
    await region.getByRole("button", { name: "样式", exact: true }).click();
  }
  async function viewHistory(id: string) {
    await page.getByRole("tab", { name: /^运行 / }).click();
    await page
      .locator(".research-content-manager")
      .getByRole("button", { name: new RegExp("^#" + id.slice(0, 8)) })
      .click();
  }
  async function checkDownload(runId: string, index = "0") {
    await region.getByRole("button", { name: "导出", exact: true }).click();
    await expect(
      region.getByRole("link", { name: "下载实际成果", exact: true }),
    ).toHaveAttribute("href", `/api/jobs/${runId}/artifacts/${index}/download`);
    await region.getByRole("button", { name: "导出", exact: true }).click();
  }

  async function run() {
    const request = page.waitForResponse(
      (r) => r.url().endsWith("/execute") && r.request().method() === "POST",
      { timeout: 30000 },
    );
    await page
      .locator(".research-context")
      .getByRole("button", { name: "预检并执行", exact: true })
      .click();
    const response = await request;
    expect(response.status()).toBe(202);
    const job = await response.json();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/jobs/${job.id}`)).json()).status,
        { timeout: 210000, intervals: [500, 1000, 2000] },
      )
      .toBe("succeeded");
    await expect(
      region.getByRole("status", { name:"图层就绪", exact: true }),
    ).toBeVisible({ timeout: 90000 });
    return job.id;
  }
  const first = await run();
  const frozen = await (
    await page.request.get(`/api/jobs/${first}/result`)
  ).json();
  const descriptor = await (
    await page.request.get(`/api/jobs/${first}/descriptor`)
  ).json();
  expect(descriptor.primary.role).toBe("composite");
  expect(descriptor.primary.sha256).not.toBe(asset.sha256);
  expect(frozen.data.operator).not.toBe("valid_mask");
  expect(descriptor.statistics.total_pixels).toBe(
    asset.facts.width * asset.facts.height,
  );
  expect(descriptor.outputs.map((o: { role: string }) => o.role)).toEqual([
    "composite",
    "indicator",
    "contribution",
    "quality",
  ]);
  await expect(region.getByLabel("成果图层", { exact: true })).toHaveValue("0");
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [1920, 1080],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    await region
      .getByRole("toolbar", { name: "成果工具条" })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: evidencePath(`actual-composite-${width}.png`),
    });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width! + 1);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const index of ["1", "2", "3", "0"]) {
    await region.getByLabel("成果图层", { exact: true }).selectOption(index);
    // Selection and visibility are independent; explicitly display this output.
    await page.getByRole("complementary", { name: "研究内容管理器" })
      .getByRole("checkbox", { name: /^显示 / }).nth(Number(index)).check();
    await expect(
      region.getByRole("status", { name:"图层就绪", exact: true }),
    ).toBeVisible({ timeout: 90000 });
    await checkDownload(first, index);
  }
  const inspected = page.waitForResponse(
    (r) =>
      r.url().includes(`/jobs/${first}/artifacts/0/inspect`) &&
      r.request().method() === "POST",
  );
  await region
    .getByRole("region", { name: "资料地图", exact: true })
    .click({ position: { x: 240, y: 180 } });
  const pixel = await (await inspected).json();
  expect(pixel.sha256).toBe(descriptor.primary.sha256);
  await expect(inspector.getByLabel("点查结果", { exact: true })).toBeVisible();
  await region.getByRole("button", { name: "样式", exact: true }).click();
  await inspector
    .getByRole("slider", { name: "不透明度", exact: true })
    .fill("0.6");
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  await region.getByRole("button", { name: "样式", exact: true }).click();
  await region.getByRole("button", { name: "详情", exact: true }).click();
  await inspector.getByText("查看实际统计表", { exact: true }).click();
  await expect(
    inspector.getByRole("table", { name: "成果全域分布", exact: true }),
  ).toBeVisible();
  expect(
    frozen.data.statistics.histogram.counts.reduce(
      (a: number, b: number) => a + b,
      0,
    ),
  ).toBe(frozen.data.statistics.valid_pixels);
  await region.getByRole("button", { name: "导出", exact: true }).click();
  const downloaded = page.waitForEvent("download");
  await region.getByRole("link", { name: "下载实际成果", exact: true }).click();
  const download = await downloaded;
  const path = await download.path();
  expect(await hash(path!)).toBe(descriptor.primary.sha256);
  await region.getByRole("button", { name: "导出", exact: true }).click();
  await page.getByRole("link", { name: "数据资源", exact: true }).click();
  await page.getByRole("link", { name: "研究工作台", exact: true }).click();
  await styleValue();
  await apply("反向工程评价");
  const second = await run();
  expect(second).not.toBe(first);
  const secondData = await (
    await page.request.get(`/api/jobs/${second}/result`)
  ).json();
  expect(secondData.data.method_snapshot.id).toBe(negative.id);
  const draftResponse = await page.request.get("/api/tasks/" + taskId);
  expect(draftResponse.status()).toBe(200);
  const currentDraft = await draftResponse.json();
  await viewHistory(first);
  await checkDownload(first);
  await styleValue();
  expect(await (await page.request.get("/api/tasks/" + taskId)).json()).toEqual(
    currentDraft,
  );
  expect(
    await (await page.request.get(`/api/jobs/${first}/result`)).json(),
  ).toEqual(frozen);
  // A was separately completed through UI in desktop-research. Here a controlled numeric fixture verifies branch switching in this same project/build.
  const numericMethod = await method("无空间工程评价", true, "csv");
  const csv = (
    await (
      await page.request.post(`/api/projects/${project}/assets`, {
        headers,
        multipart: {
          file: {
            name: "nonspatial.csv",
            mimeType: "text/csv",
            buffer: Buffer.from("id,distance\n001,500000\n002,1000000\n"),
          },
        },
      })
    ).json()
  ).asset;
  const csvTask = await (
    await page.request.post("/api/tasks", {
      headers,
      data: {
        project_id: project,
        title: "A 无空间分支切换",
        purpose: "assessment",
      },
    })
  ).json();
  const draft = {
    ...csvTask.draft,
    selection: [{ asset_id: csv.id, revision: 1 }],
    mapping: [
      { asset_id: csv.id, field: "table/id", role: "identity" },
      {
        asset_id: csv.id,
        field: "table/distance",
        concept: "distance",
        unit: "m",
        support: "point",
        role: "feature",
      },
    ],
    method_id: numericMethod.id,
    options: { method_revision: 1 },
  };
  expect(
    (
      await page.request.put(`/api/tasks/${csvTask.id}`, {
        headers,
        data: { expected_revision: 1, draft },
      })
    ).ok(),
  ).toBe(true);
  const numeric = await (
    await page.request.post(`/api/tasks/${csvTask.id}/execute`, {
      headers,
      data: { expected_revision: 2, idempotency_key: "numeric-switch" },
    })
  ).json();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${numeric.id}`)).json())
          .status,
    )
    .toBe("succeeded");
  async function openResult(query: string) {
    await page.getByRole("link", { name: "成果管理", exact: true }).click();
    const catalog = page.getByRole("region", { name: "成果管理", exact: true });
    await catalog.getByLabel("搜索成果管理", { exact: true }).fill(query);
    await catalog.getByLabel("搜索成果管理", { exact: true }).press("Enter");
    await catalog
      .getByRole("button", { name: "查看成果", exact: true })
      .first()
      .click();
  }
  await openResult("A 无空间");
  await expect(
    region.getByRole("table", { name: "观测结果", exact: true }),
  ).toBeVisible();
  await expect(
    region.getByRole("region", { name: "资料地图", exact: true }),
  ).toHaveCount(0);
  await expect(region.getByLabel("本次实际空间成果")).toHaveCount(0);
  await page.screenshot({
    path: evidencePath("nonspatial-table-after-raster.png"),
  });
  await openResult(currentDraft.draft.title);
  await expect(
    region.getByRole("region", { name: "资料地图", exact: true }),
  ).toBeVisible();
  await expect(
    region.getByRole("table", { name: "观测结果", exact: true }),
  ).toHaveCount(0);
  await viewHistory(first);
  await checkDownload(first);
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/projects/${project}/workspace-state`)
          ).json()
        ).state.viewed_job_id,
    )
    .toBe(first);
  await page.reload();
  await styleValue();
  // An old descriptor deliberately arrives after another historical run is selected.
  let fulfilledOld!: () => void;
  const fulfilled = new Promise<void>((resolve) => {
    fulfilledOld = resolve;
  });
  let releaseOld!: () => void;
  const released = new Promise<void>((resolve) => {
    releaseOld = resolve;
  });
  let requestStarted!: () => void;
  const started = new Promise<void>((resolve) => {
    requestStarted = resolve;
  });
  await page.route(`**/jobs/${first}/descriptor`, async (route) => {
    const response = await route.fetch();
    requestStarted();
    await released;
    await route.fulfill({ response });
    fulfilledOld();
  });
  await page.reload();
  await started;
  await viewHistory(second);
  await checkDownload(second);
  releaseOld();
  await fulfilled;
  await page.unroute(`**/jobs/${first}/descriptor`);
  await checkDownload(second);
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("result-branches.json"),
    JSON.stringify(
      {
        project,
        task_id: taskId,
        source: asset,
        first_run: first,
        second_run: second,
        numeric_run: numeric.id,
        numeric_task: csvTask.id,
        positive_method: positive.id,
        negative_method: negative.id,
        descriptor,
        pixel,
        source_bytes: asset.size,
        statistics: frozen.data.statistics,
        science_fills: 2,
        support_choice: 1,
        engineering_reference: true,
        formal_business_validated: false,
        A_switch: "PASS",
        B_raster_browser: "PASS",
        historical_draft_unchanged: "PASS",
        download_hash: descriptor.primary.sha256,
      },
      null,
      2,
    ),
  );
});
