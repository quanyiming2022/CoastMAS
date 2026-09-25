import { evidenceDirectory, evidencePath } from "./evidence";
import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
test("new workspace: file facts, server draft recovery, actual worker and complete result", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  if (!accessFile) throw new Error("Explicit isolated access file required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  async function login(target: typeof page) {
    await target.goto("/?project=" + access.project_id);
    await target.getByLabel("邮箱", { exact: true }).fill(access.email);
    await target.getByLabel("密码", { exact: true }).fill(access.password);
    await target.getByRole("button", { name: "登录", exact: true }).click();
    await expect(
      target.getByRole("heading", { name: "科研任务", exact: true }),
    ).toBeVisible();
  }
  await login(page);
  await page.getByLabel("任务名称", { exact: true }).fill("新批次真实文件检查");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await page.getByLabel("添加资料", { exact: true }).setInputFiles({
    name: "observations.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id;distance\n001;0\n002;12\n"),
  });
  await expect(
    page.getByText("observations.csv", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("分隔符表格 · 文件未明确声明规范版本", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("任务名称", { exact: true }).fill("保存后关闭也能恢复");
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  const taskURL = page.url();
  const context = await browser.newContext();
  const restored = await context.newPage();
  await login(restored);
  await restored.goto(taskURL);
  await expect(restored.getByLabel("任务名称", { exact: true })).toHaveValue(
    "保存后关闭也能恢复",
  );
  await restored
    .getByRole("button", { name: "预检并执行", exact: true })
    .click();
  await expect(restored.getByText("工程执行成功", { exact: true })).toBeVisible(
    { timeout: 30000 },
  );
  const download = restored.waitForEvent("download");
  await restored
    .getByRole("link", { name: "下载完整成果", exact: true })
    .click();
  const file = await download;
  const path = await file.path();
  if (!path) throw new Error("Missing real download");
  const output = JSON.parse(await readFile(path, "utf8"));
  expect(output.data.datasets[0].facts.layers[0].row_count).toBe(2);
  expect(output.states.business_validated).toBe(false);
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await restored.setViewportSize({ width: width!, height: height! });
    expect(
      await restored.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width! + 1);
    await restored.screenshot({
      path: evidencePath(`workspace-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("interaction-counts.json"),
    JSON.stringify(
      {
        scope: "single actual inspection journey; login excluded",
        text_fill_events: 2,
        file_selection_events: 1,
        task_submit_events: 1,
        preflight_run_events: 1,
        download_events: 1,
        scientific_manual_fields: 0,
        recovery_retyped_fields: 0,
        note: "Test-defined operation counts; not human time or all-purpose usability acceptance",
      },
      null,
      2,
    ),
  );
  await context.close();
});

test("navigation saves the last keystroke before leaving and back restores it", async ({
  page,
}) => {
  if (!accessFile) throw new Error("Explicit isolated access required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByLabel("任务名称", { exact: true }).fill("导航恢复测试");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  const field = page.getByLabel("任务名称", { exact: true });
  await field.fill("最后一个字也必须保存");
  await page.getByRole("link", { name: "研究工作台", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "最后一个字也必须保存",
  );
});
