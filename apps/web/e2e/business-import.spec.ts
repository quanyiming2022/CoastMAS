import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { test, expect } from "@playwright/test";
async function digest(path: string) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}
test("real business files become immutable assets; full size TIFF uploads and downloads", async ({
  page,
}) => {
  test.setTimeout(600000);
  const root = process.env.COASTMAS_E2E_BUSINESS_ROOT;
  if (!root)
    throw new Error(
      "COASTMAS_E2E_BUSINESS_ROOT required: no synthetic substitute",
    );
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  const project = await page.locator("#project-select").inputValue();
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "coastmas_csrf",
  )!.value;
  const list = await page.request.get(
    `/api/v1/data-assets/local-files?project_id=${project}&source=business-acceptance&limit=500`,
  );
  expect(list.ok()).toBeTruthy();
  const inventory = await list.json();
  expect(inventory.total).toBe(40);
  const large = inventory.files.find(
    (file: { size_bytes: number }) => file.size_bytes > 64 * 1024 ** 2,
  );
  expect(large).toBeTruthy();
  await page.goto("/data/import");
  await page.getByLabel("原始影像文件").setInputFiles(join(root, large.path));
  await page
    .getByLabel("数据名称", { exact: true })
    .fill("真实大影像完整导入验收");
  await page
    .getByLabel("数据来源", { exact: true })
    .fill("开放网站（用户声明）");
  await page.getByLabel("使用许可", { exact: true }).fill("非商业（用户声明）");
  await page.getByLabel("所属年份（可留空）").fill("2022");
  const response = page.waitForResponse(
    (result) =>
      result.url().endsWith("/data-assets/ingest") &&
      result.request().method() === "POST",
    { timeout: 180000 },
  );
  await page
    .getByRole("button", { name: "导入为数据资产", exact: true })
    .click();
  const imported = await response;
  expect(imported.status(), await imported.text()).toBe(201);
  const first = (await imported.json()).spec;
  expect(first.quality.size_bytes).toBe(large.size_bytes);
  expect(first.quality.file_facts.width).toBe(11416);
  expect(first.quality.file_facts.height).toBe(9000);
  expect(first.quality.validated).toBe(false);
  expect(first.variables).toEqual([]);
  expect(first.checksum).toBe(await digest(join(root, large.path)));
  await expect(
    page.getByRole("heading", { name: "数据版本管理", exact: true }),
  ).toBeVisible();
  const downloading = page.waitForEvent("download", { timeout: 120000 });
  await page.getByRole("link", { name: "下载此版本原始文件" }).click();
  const downloaded = await downloading;
  expect(await downloaded.failure()).toBeNull();
  expect(await digest((await downloaded.path())!)).toBe(first.checksum);
  await page.getByRole("button", { name: "读取实际文件预览" }).click();
  await expect(
    page.getByRole("heading", { name: "实际文件预览", exact: true }),
  ).toBeVisible({ timeout: 120000 });
  const evidence = [
    {
      path: large.path,
      id: first.id,
      checksum: first.checksum,
      size: large.size_bytes,
      method: "browser_upload_download",
    },
  ];
  for (const file of inventory.files.filter(
    (file: { path: string }) => file.path !== large.path,
  )) {
    const result = await page.request.post("/api/v1/data-assets/ingest-local", {
      headers: { "X-CSRF-Token": csrf },
      timeout: 180000,
      data: {
        project_id: project,
        source: "business-acceptance",
        path: file.path,
        declaration: {
          name: file.path,
          source: "开放网站（用户声明）",
          license: "非商业（用户声明）",
          year: 2022,
        },
      },
    });
    expect(result.status(), await result.text()).toBe(201);
    const asset = (await result.json()).spec;
    expect(asset.checksum).toBe(await digest(join(root, file.path)));
    expect(asset.quality.size_bytes).toBe(file.size_bytes);
    expect(asset.variables).toEqual([]);
    expect(asset.quality.validated).toBe(false);
    evidence.push({
      path: file.path,
      id: asset.id,
      checksum: asset.checksum,
      size: file.size_bytes,
      method: "authorized_local_import",
    });
  }
  await mkdir("../../artifacts/business-import", { recursive: true });
  await writeFile(
    "../../artifacts/business-import/real-assets.json",
    JSON.stringify(
      {
        scope: "isolated_engineering_asset_ingestion_not_scientific_execution",
        assets: evidence,
      },
      null,
      2,
    ),
  );
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto("/data/import");
    await page.getByLabel("接入方式").selectOption("local");
    await page.getByLabel("已授权来源").selectOption("business-acceptance");
    await expect(
      page.getByRole("table", { name: "可导入原始文件" }),
    ).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(viewport.width + 1);
    await page.screenshot({
      path: `../../artifacts/business-import/local-${viewport.width}.png`,
      fullPage: true,
    });
  }
});
