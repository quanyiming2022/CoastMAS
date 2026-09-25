import { evidenceDirectory, evidencePath } from "./evidence";
import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";

test("batch upload preserves successes and resumes one failed file after refresh", async ({
  page,
}) => {
  test.setTimeout(90000);
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access file required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByLabel("任务名称", { exact: true }).fill("批量资料与失败恢复");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await page.getByLabel("添加资料", { exact: true }).setInputFiles([
    {
      name: "first-batch.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,v\n1,2\n"),
    },
    {
      name: "failed-batch.csv",
      mimeType: "application/octet-stream",
      buffer: Buffer.alloc(10),
    },
    {
      name: "last-batch.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,v\n3,4\n"),
    },
  ]);
  await expect(
    page
      .getByRole("navigation", { name: "任务资料列表" })
      .getByRole("button", { name: "last-batch.csv", exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("添加资料", { exact: true })).toBeEnabled();
  const url = page.url();
  await page.reload();
  await page.getByText("接入批次与恢复（1 批）", { exact: true }).click();
  await expect(
    page.getByText("批次 1 · 2/3 已接入", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("重选 failed-batch.csv", { exact: true })
    .setInputFiles({
      name: "failed-batch.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,v\n2,33\n"),
    });
  await expect(page.getByLabel("添加资料", { exact: true })).toBeEnabled();
  await expect(
    page
      .getByRole("navigation", { name: "任务资料列表" })
      .getByRole("button", { name: "failed-batch.csv", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "预检并执行", exact: true }).click();
  await expect(page.getByText("工程执行成功", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const file = await (await download).path();
  if (!file) throw new Error("Actual download missing");
  const result = JSON.parse(await readFile(file, "utf8"));
  expect(result.manifest.assets).toHaveLength(3);
  expect(
    new Set(result.manifest.assets.map((a: { sha256: string }) => a.sha256))
      .size,
  ).toBe(3);
  await mkdir(evidenceDirectory, { recursive: true });
  await writeFile(
    evidencePath("batch-recovery.json"),
    JSON.stringify(
      {
        status: "PASS",
        url,
        selected: 3,
        failed: 1,
        retry_files: 1,
        final_assets: 3,
        duplicated_assets: 0,
        recovery: "server batch restored after full refresh",
        internal_json_edits: 0,
      },
      null,
      2,
    ),
  );
});
