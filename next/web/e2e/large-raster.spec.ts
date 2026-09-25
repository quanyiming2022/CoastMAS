import { evidenceDirectory, evidencePath } from "./evidence";
import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { createHash } from "node:crypto";
const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
const actualFile = process.env.COASTMAS_NEXT_REAL_RASTER;
async function sha(path: string) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
test("actual large raster browser upload, real preview and full byte download", async ({
  page,
}) => {
  test.setTimeout(240000);
  if (!accessFile || !actualFile)
    throw new Error("Explicit isolated access and real raster paths required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  const source = await stat(actualFile);
  expect(source.size).toBeGreaterThan(64 * 1024 * 1024);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const basemapResponses: number[] = [];
  page.on("response", (reply) => {
    if (reply.url().startsWith("https://tile.openstreetmap.org/"))
      basemapResponses.push(reply.status());
  });
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("真实珠三角大栅格浏览器验收");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  await page.getByLabel("添加资料", { exact: true }).setInputFiles(actualFile);
  await expect(
    page.getByRole("heading", { name: "PRD_distance_water.tif", exact: true }),
  ).toBeVisible({ timeout: 90000 });
  await expect(
    page.getByRole("button", { name: "查看实际空间预览", exact: true }),
  ).toHaveCount(0);
  const map = page.getByRole("region", { name: "资料地图", exact: true });
  await expect(map.locator("canvas")).toBeVisible();
  await expect(page.getByRole("status", { name:"图层就绪", exact: true })).toBeVisible(
    { timeout: 60000 },
  );
  const taskId = page.url().split("/").pop();
  const before = await (await page.request.get(`/api/tasks/${taskId}`)).json();
  await page.getByLabel("不透明度", { exact: true }).fill("0.4");
  await page.getByLabel("显示数据层", { exact: true }).uncheck();
  await expect(page.getByText("个人视图已保存", { exact: true })).toBeVisible();
  await page.reload();
  await expect(
    page.getByLabel("显示数据层", { exact: true }),
  ).not.toBeChecked();
  await expect(page.getByLabel("不透明度", { exact: true })).toHaveValue("0.4");
  await page.getByLabel("显示数据层", { exact: true }).check();
  await page.getByLabel("不透明度", { exact: true }).fill("0.9");
  await expect(page.getByText("个人视图已保存", { exact: true })).toBeVisible();
  const after = await (await page.request.get(`/api/tasks/${taskId}`)).json();
  expect(after.draft).toEqual(before.draft);
  expect(after.revision).toEqual(before.revision);
  const attribution = page.locator(".maplibregl-ctrl-attrib-button");
  expect(
    await attribution.evaluate((node) => node.getBoundingClientRect().height),
  ).toBeLessThanOrEqual(30);
  const downloaded = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载原始资料", exact: true }).click();
  const download = await downloaded;
  const output = await download.path();
  if (!output) throw new Error("Download missing");
  expect((await stat(output)).size).toBe(source.size);
  const originalHash = await sha(actualFile);
  expect(await sha(output)).toBe(originalHash);
  await mkdir(evidenceDirectory, { recursive: true });
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
      path: evidencePath(`large-raster-${width}.png`),
      fullPage: true,
    });
  }
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("large-raster.json"),
    JSON.stringify(
      {
        bytes: source.size,
        sha256: originalHash,
        full_upload_download: "PASS",
        real_preview: "PASS",
        page_errors: errors,
        basemap_responses: basemapResponses,
        basemap_live: basemapResponses.some((status) => status === 200)
          ? "PASS"
          : "BLOCKED",
        manual_operations: {
          login_excluded: true,
          task_name_fills: 1,
          task_creation: 1,
          file_selection: 1,
          preview_open: 0,
          display_restore_check: true,
          download: 1,
          format_selections: 0,
          metadata_reentry: 0,
        },
        task_url: page.url(),
      },
      null,
      2,
    ),
  );
});
