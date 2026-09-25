import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir, stat } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { createHash } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";
async function sha(path: string) {
  const h = createHash("sha256");
  for await (const chunk of createReadStream(path)) h.update(chunk);
  return h.digest("hex");
}

test("real professional first chain: catalog lifecycle, native image and actual full-grid result", async ({
  page,
}) => {
  test.setTimeout(240000);
  const file = process.env.COASTMAS_NEXT_CONSTRUCTION_RASTER;
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!file || !accessFile)
    throw new Error(
      "Explicit real construction raster and isolated credentials required",
    );
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/library?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  const user = await (await page.request.get("/api/session")).json();
  const made = await page.request.post("/api/projects", {
    headers: { "X-CSRF-Token": user.csrf },
    data: { name: "专业工作台真实验收 " + Date.now() },
  });
  expect(made.status()).toBe(201);
  const project = (await made.json()).id;
  await page.goto("/library?project=" + project);
  const complete = page.waitForResponse(
    (r) => r.url().endsWith("/complete") && r.request().method() === "POST",
  );
  await page.getByLabel("导入并查看资料", { exact: true }).setInputFiles(file);
  const upload = await (await complete).json();
  const asset = upload.asset;
  expect(asset.size).toBe((await stat(file)).size);
  expect(asset.size).toBeGreaterThan(64 * 1024 ** 2);
  await expect(page.getByRole("status", { name:"图层就绪", exact: true })).toBeVisible(
    { timeout: 90000 },
  );
  expect(
    await (await page.request.get(`/api/projects/${project}/tasks`)).json(),
  ).toHaveLength(0);
  await mkdir(evidenceDirectory, { recursive: true });
  const layouts = [];
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    const canvas = await page
      .getByRole("region", { name: "资料地图", exact: true })
      .boundingBox();
    const app = await page.locator(".workspace-main").boundingBox();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width! + 1);
    if (width! > 700) {
      expect(canvas!.width).toBeGreaterThanOrEqual(680);
      expect(canvas!.width).toBeGreaterThanOrEqual(app!.width * 0.5);
      expect(canvas!.height).toBeGreaterThanOrEqual((height! - 48) * 0.6);
    }
    layouts.push({ width, height, canvas, app });
    await page.screenshot({
      path: evidencePath(`professional-source-${width}.png`),
    });
  }
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "移动导航" })).toBeVisible();
  await page.screenshot({ path: evidencePath("professional-mobile-nav.png") });
  await page.keyboard.press("Escape");
  await expect(
    page.getByRole("button", { name: "打开导航", exact: true }),
  ).toBeFocused();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page
    .getByRole("button", { name: "修改 " + asset.name, exact: true })
    .click();
  await page
    .getByLabel("显示名称", { exact: true })
    .fill("珠三角建设用地距离 · 2022");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "修改目录信息" })).toHaveCount(
    0,
  );
  await page.getByLabel("查找资料", { exact: true }).fill("珠三角");
  await page.getByLabel("查找资料", { exact: true }).press("Enter");
  await expect(
    page.getByRole("button", {
      name: "珠三角建设用地距离 · 2022",
      exact: true,
    }),
  ).toBeVisible();
  await page
    .getByLabel("选择 珠三角建设用地距离 · 2022", { exact: true })
    .check();
  await page.getByRole("button", { name: "回收所选", exact: true }).click();
  await page.getByRole("button", { name: "确认回收", exact: true }).click();
  await expect(
    page.getByText("1 项已回收；0 项未执行。", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "珠三角建设用地距离 · 2022",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("combobox", { name: "范围", exact: true })
    .selectOption("recycled");
  await page
    .getByLabel("选择 珠三角建设用地距离 · 2022", { exact: true })
    .check();
  await page.getByRole("button", { name: "恢复所选", exact: true }).click();
  await page.getByRole("button", { name: "确认恢复", exact: true }).click();
  await expect(
    page.getByText("1 项已恢复；0 项未执行。", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "完成", exact: true }).click();
  await page
    .getByRole("combobox", { name: "范围", exact: true })
    .selectOption("active");
  await page.getByRole("button", { name: "生成有效覆盖", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  const taskId = page.url().split("/").pop();
  const execution = page.waitForResponse(
    (r) => r.url().endsWith("/execute") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "预检并执行", exact: true }).click();
  const job = await (await execution).json();
  const result = page.getByLabel("本次实际空间成果", { exact: true });
  await expect(
    result.getByRole("status", { name:"图层就绪", exact: true }),
  ).toBeVisible({ timeout: 120000 });
  const descriptor = await (
    await page.request.get(`/api/jobs/${job.id}/descriptor`)
  ).json();
  expect(descriptor.primary.sha256).not.toBe(asset.sha256);
  expect(descriptor.statistics.total_pixels).toBe(
    asset.facts.width * asset.facts.height,
  );
  const frozen = await (
    await page.request.get(`/api/jobs/${job.id}/result`)
  ).json();
  await result.getByLabel("不透明度", { exact: true }).fill("0.4");
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  await page.reload();
  await expect(result.getByLabel("不透明度", { exact: true })).toHaveValue(
    "0.4",
  );
  expect(
    await (await page.request.get(`/api/jobs/${job.id}/result`)).json(),
  ).toEqual(frozen);
  await result.getByLabel("不透明度", { exact: true }).fill("0.9");
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  await result
    .getByRole("region", { name: "资料地图", exact: true })
    .click({ position: { x: 300, y: 200 } });
  await expect(result.getByLabel("点查结果", { exact: true })).toBeVisible();
  const download = page.waitForEvent("download");
  await result.getByRole("link", { name: "下载实际成果", exact: true }).click();
  const path = await (await download).path();
  expect(path).not.toBeNull();
  expect(await sha(path!)).toBe(descriptor.primary.sha256);
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width! + 1);
    const bounds = await result
      .getByRole("region", { name: "资料地图", exact: true })
      .boundingBox();
    expect(bounds!.y + 100).toBeLessThan(height!);
    await page.screenshot({
      path: evidencePath(`professional-result-${width}.png`),
    });
  }
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("professional-first-chain.json"),
    JSON.stringify(
      {
        project,
        task_id: taskId,
        run_id: job.id,
        source: {
          id: asset.id,
          name: asset.name,
          bytes: asset.size,
          sha256: asset.sha256,
          width: asset.facts.width,
          height: asset.facts.height,
        },
        descriptor,
        layouts,
        errors,
        manual_operations: {
          upload_file_choice: 1,
          task_name_fills: 0,
          scientific_fills: 0,
          boundary_draws: 0,
          asset_reselections: 0,
          method_parameter_fills: 0,
          analysis_action: 1,
          execute_action: 1,
          lifecycle_exercise_excluded: true,
        },
        download_sha256: await sha(path!),
      },
      null,
      2,
    ),
  );
});
