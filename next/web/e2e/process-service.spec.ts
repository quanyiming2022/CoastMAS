import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("standard process execution uses the same browser task and downloadable evidence", async ({
  page,
}) => {
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("标准服务实际实体提取 " + Date.now());
  await page
    .getByRole("combobox", { name: "任务类型", exact: true })
    .selectOption("entities");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  const uploaded = page.waitForResponse(
    (r) => r.url().endsWith("/content") && r.request().method() === "POST",
  );
  await page.getByLabel("添加资料", { exact: true }).setInputFiles({
    name: "standard-entities.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(
      JSON.stringify({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            id: "001",
            properties: { pressure: 0 },
            geometry: { type: "Point", coordinates: [113.2, 22.5] },
          },
        ],
      }),
    ),
  });
  const intake = await uploaded;
  expect(intake.status()).toBe(200);
  expect((await intake.json()).status).toBe("ready");
  const taskId = new URL(page.url()).pathname.split("/").at(-1);
  const task = await (await page.request.get(`/api/tasks/${taskId}`)).json();
  const session = await (await page.request.get("/api/session")).json();
  const root = "/api/ogc/1.0";
  expect((await page.request.get(root + "/processes/entities")).status()).toBe(
    200,
  );
  const response = await page.request.post(
    root + "/processes/entities/execution",
    {
      headers: { "X-CSRF-Token": session.csrf, Prefer: "respond-async" },
      data: {
        inputs: {
          task: {
            value: { id: task.id, revision: task.revision },
            mediaType: "application/json",
          },
        },
        response: "document",
      },
    },
  );
  expect(response.status()).toBe(201);
  const queued = await response.json();
  const location = response.headers().location;
  await expect
    .poll(
      async () => (await (await page.request.get(location)).json()).status,
      { timeout: 30000 },
    )
    .toBe("successful");
  const standard = await (await page.request.get(location + "/results")).json();
  const result = await (await page.request.get(standard.result.href)).json();
  expect(result.data.features[0].id).toBe("001");
  expect(result.data.features[0].properties.pressure).toBe(0);
  expect(result.manifest.task_id).toBe(task.id);
  expect(result.manifest.draft_revision).toBe(task.revision);
  await page.reload();
  await expect(
    page.getByRole("link", { name: "下载完整成果", exact: true }),
  ).toHaveAttribute("href", `/api/jobs/${queued.jobID}/download`);
  const downloading = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const file = await (await downloading).path();
  if (!file) throw new Error("Actual browser download missing");
  expect(JSON.parse(await readFile(file, "utf8"))).toEqual(result);
  await mkdir(evidenceDirectory, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByRole("table", { name: "完整实体属性" })).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "完整实体属性", exact: true })
      .getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.abort(),
  );
  await page
    .getByRole("button", { name: "在地图定位 001", exact: true })
    .click();
  const map = page.getByRole("region", { name: "实体成果地图", exact: true });
  await expect(map.locator("canvas")).toBeVisible();
  await expect(
    page.getByText("互联网底图不可用，仍可查看实际实体层", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("地图显示全部 1 个实际实体。", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "在地图定位 001", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(
    page.getByText("实际实体层已绘制", { exact: true }),
  ).toBeVisible();
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 1);
    await expect(async () => {
      const screenshot = await map.screenshot({
        path: evidencePath(`entity-map-${width}.png`),
      });
      const selectedPixels = await page.evaluate(async (encoded) => {
        const image = new Image();
        image.src = "data:image/png;base64," + encoded;
        await image.decode();
        const canvas = document.createElement("canvas");
        canvas.width = image.width;
        canvas.height = image.height;
        const context = canvas.getContext("2d")!;
        context.drawImage(image, 0, 0);
        const pixels = context.getImageData(
          0,
          0,
          image.width,
          image.height,
        ).data;
        let count = 0;
        for (let i = 0; i < pixels.length; i += 4) {
          if (
            pixels[i]! > 130 &&
            pixels[i + 1]! < 145 &&
            pixels[i + 2]! < 90 &&
            pixels[i + 3]! > 200
          )
            count++;
        }
        return count;
      }, screenshot.toString("base64"));
      expect(
        selectedPixels,
        "Actual selected entity must be painted, not an empty map",
      ).toBeGreaterThan(20);
    }).toPass({ timeout: 10000 });
  }
  const bounds = await map.boundingBox();
  if (!bounds) throw new Error("Actual map bounds missing");
  await map.click({ position: { x: bounds.width / 2, y: bounds.height / 2 } });
  await expect(page.getByText("当前选择：001", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: evidencePath("process-service-1440.png"),
    fullPage: true,
  });
  await writeFile(
    evidencePath("process-service.json"),
    JSON.stringify(
      {
        task_id: task.id,
        job_id: queued.jobID,
        standard_and_browser_result_equal: true,
        actual_features: result.data.features.length,
        frozen_revision: task.revision,
        no_scientific_fields_invented: true,
        actual_map_and_table: true,
        offline_basemap_fallback: true,
        conformance: "document_reference_async_subset",
      },
      null,
      2,
    ),
  );
});
