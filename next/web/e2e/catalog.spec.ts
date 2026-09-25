import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("catalog upload immediately renders real raster, native inspect and persisted view without a task", async ({
  page,
  browser,
}) => {
  test.setTimeout(240000);
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  const raster = process.env.COASTMAS_NEXT_REAL_RASTER;
  if (!accessFile || !raster)
    throw new Error("Explicit isolated credentials and actual raster required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort(),
  );
  await page.goto("/library?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  const user = await (await page.request.get("/api/session")).json();
  const projectResponse = await page.request.post("/api/projects", {
    headers: { "X-CSRF-Token": user.csrf },
    data: { name: "目录真实影像验收 " + Date.now() },
  });
  expect(projectResponse.status()).toBe(201);
  const project = (await projectResponse.json()).id;
  expect(typeof project).toBe("string");
  await page.goto("/library?project=" + project);
  await expect(
    page.getByText("暂无资料，可直接导入查看。", { exact: true }),
  ).toBeVisible();
  await mkdir(evidenceDirectory, { recursive: true });
  if (process.env.COASTMAS_CAPTURE_BEFORE) {
    for (const [width, height] of [
      [1440, 900],
      [1366, 768],
      [390, 844],
    ]) {
      await page.setViewportSize({ width: width!, height: height! });
      await page.screenshot({
        path: evidencePath(`catalog-before-${width}.png`),
        fullPage: true,
      });
    }
  }
  const before = await page.request.get(`/api/projects/${project}/tasks`);
  expect(before.status()).toBe(200);
  const taskCount = (await before.json()).length;
  expect(taskCount).toBe(0);
  const started = Date.now();
  const submitted = page.waitForResponse(
    (reply) =>
      /\/uploads\/[^/]+\/complete$/.test(reply.url()) &&
      reply.request().method() === "POST",
  );
  await page
    .getByLabel("导入并查看资料", { exact: true })
    .setInputFiles(raster);
  const response = await submitted;
  expect(response.status()).toBe(200);
  const asset = (await response.json()).asset;
  const commitMs = Date.now() - started;
  const region = page.getByRole("region", { name: "资料地图", exact: true });
  await expect(region.locator("canvas")).toBeVisible({ timeout: 90000 });
  await expect(page.getByRole("status", { name:"图层就绪", exact: true })).toBeVisible(
    { timeout: 60000 },
  );
  const firstLayerMs = Date.now() - started;
  await expect(
    page.getByText("原始数值；文件未声明单位", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("个人视图已保存", { exact: true })).toBeVisible();
  const tasks = await page.request.get(`/api/projects/${project}/tasks`);
  expect((await tasks.json()).length).toBe(taskCount);
  const screenshot = await region.screenshot();
  const positions = await page.evaluate(async (encoded) => {
    const image = new Image();
    image.src = "data:image/png;base64," + encoded;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, image.width, image.height).data;
    const locations: { x: number; y: number }[] = [];
    for (let y = 40; y < image.height - 40; y += 8)
      for (let x = 40; x < image.width - 40; x += 8) {
        const i = (y * image.width + x) * 4;
        if (
          pixels[i + 1]! > pixels[i]! + 20 &&
          pixels[i + 2]! > pixels[i]! + 15 &&
          pixels[i]! < 190
        )
          locations.push({ x, y });
      }
    return locations;
  }, screenshot.toString("base64"));
  expect(
    positions.length,
    "Actual raster pixels must be painted even with basemap offline",
  ).toBeGreaterThan(5);
  let inspectedResponse;
  for (const position of positions.slice(0, 20)) {
    const inspected = page.waitForResponse((reply) =>
      reply.url().endsWith(`/assets/${asset.id}/inspect`),
    );
    await region.locator("canvas").click({ position });
    inspectedResponse = await inspected;
    if ((await inspectedResponse.json()).valid) break;
  }
  if (!inspectedResponse) throw new Error("No original pixel request");
  const native = await inspectedResponse.json();
  expect(native.valid).toBe(true);
  expect(native.value).not.toBeNull();
  expect(native.sha256).toBe(asset.sha256);
  await expect(
    page.getByRole("heading", { name: "原生像元点查", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("源像元（非显示采样）", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(region.locator("canvas")).toBeVisible();
  await expect(page.getByRole("status", { name:"图层就绪", exact: true })).toBeVisible(
    { timeout: 60000 },
  );
  await expect(
    page.getByRole("heading", { name: asset.name, exact: true }),
  ).toBeVisible();
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width! + 1);
    await page.screenshot({
      path: evidencePath(`catalog-after-${width}.png`),
      fullPage: true,
    });
  }
  const reopenedContext = await browser.newContext();
  const reopened = await reopenedContext.newPage();
  await reopened.goto("/library?project=" + project);
  await reopened.getByLabel("邮箱", { exact: true }).fill(access.email);
  await reopened.getByLabel("密码", { exact: true }).fill(access.password);
  await reopened.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    reopened.getByRole("heading", { name: asset.name, exact: true }),
  ).toBeVisible();
  await expect(
    reopened
      .getByRole("region", { name: "资料地图", exact: true })
      .locator("canvas"),
  ).toBeVisible();
  await reopenedContext.close();
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("catalog.json"),
    JSON.stringify(
      {
        project_id: project,
        asset_id: asset.id,
        native_point: native,
        sha256: asset.sha256,
        size: asset.size,
        width: asset.facts.width,
        height: asset.facts.height,
        commit_ms: commitMs,
        first_layer_ms: firstLayerMs,
        cache_condition:
          "managed bytes and display style may already be cached; not a cold-storage benchmark",
        actual_colored_pixels: positions.length,
        timing_scope:
          "browser upload start through visible actual raster; includes transfer; server render diagnostics separate",
        task_count_unchanged: true,
        reopen_without_file_reselect: true,
        page_errors: errors,
        manual_operations: {
          file_selection: 1,
          task_name: 0,
          task_creation: 0,
          scientific_fields: 0,
          boundary: 0,
          preview_open: 0,
        },
      },
      null,
      2,
    ),
  );
});

test("interrupted upload survives reload and sends only missing verified parts", async ({
  page,
}) => {
  test.setTimeout(120000);
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!accessFile) throw new Error("Isolated credentials required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  await page.goto("/library?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  const user = await (await page.request.get("/api/session")).json();
  const projectResponse = await page.request.post("/api/projects", {
    headers: { "X-CSRF-Token": user.csrf },
    data: { name: "分段中断恢复验收 " + Date.now() },
  });
  expect(projectResponse.status()).toBe(201);
  const project = (await projectResponse.json()).id;
  await page.goto("/library?project=" + project);
  const buffer = Buffer.from(
    "id,value\n" +
      Array.from(
        { length: 9000 },
        (_, i) => `${String(i).padStart(5, "0")},${"x".repeat(1000)}\n`,
      ).join(""),
  );
  const file = {
    name: "resumable-observations.csv",
    mimeType: "text/csv",
    buffer,
  };
  const requests: number[] = [];
  page.on("request", (request) => {
    const match = request.url().match(/\/parts\/(\d+)$/);
    if (match) requests.push(Number(match[1]));
  });
  await page.route("**/api/uploads/*/parts/1", (route) => route.abort());
  await page.getByLabel("导入并查看资料", { exact: true }).setInputFiles(file);
  await expect(page.getByRole("alert")).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("未完成接入（1）", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/8.00 \/ .* MiB 已保存/)).toBeVisible();
  await page.unroute("**/api/uploads/*/parts/1");
  const completed = page.waitForResponse((reply) =>
    /\/uploads\/[^/]+\/complete$/.test(reply.url()),
  );
  await page
    .getByLabel("重选原文件继续：resumable-observations.csv", { exact: true })
    .setInputFiles(file);
  const result = await completed;
  expect(result.status()).toBe(200);
  const asset = (await result.json()).asset;
  await expect(
    page.getByRole("heading", { name: file.name, exact: true }),
  ).toBeVisible();
  expect(requests.filter((index) => index === 0)).toHaveLength(1);
  expect(requests.filter((index) => index === 1)).toHaveLength(2);
  const downloaded = await page.request.get(`/api/assets/${asset.id}/download`);
  expect(await downloaded.body()).toEqual(buffer);
  await expect(page.getByText("未完成接入（1）", { exact: true })).toHaveCount(
    0,
  );
  await writeFile(
    evidencePath("upload-resume.json"),
    JSON.stringify(
      {
        project,
        asset_id: asset.id,
        sha256: asset.sha256,
        bytes: buffer.length,
        part_requests: requests,
        full_download_matches: true,
        refresh_recovery: true,
        fixture:
          "explicit synthetic transport fixture, not scientific observations",
      },
      null,
      2,
    ),
  );
});
