import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";

test("CSVW standard package automatically reads identity, decimal values and missing data in the browser", async ({
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
    .fill("CSVW标准自动读取验收");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  const fixture = fileURLToPath(
    new URL("./fixtures/csvw-standard.zip", import.meta.url),
  );
  const original = await readFile(fixture);
  await page.getByLabel("添加资料", { exact: true }).setInputFiles(fixture);
  const asset = page.getByRole("region", {
    name: "资料查看工作区",
    exact: true,
  });
  await expect(asset).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "用途 data.csv/id", exact: true }),
  ).toHaveValue("identity");
  const preview = asset.getByRole("table", {
    name: "csvw-standard.zip data.csv 原始内容预览",
    exact: true,
  });
  await expect(
    preview.getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  await expect(
    preview.getByRole("cell", { name: "1.25", exact: true }),
  ).toBeVisible();
  await expect(
    preview.getByRole("cell", { name: "缺值", exact: true }),
  ).toBeVisible();
  await expect(
    preview.getByRole("cell", { name: "否", exact: true }),
  ).toBeVisible();
  const downloading = page.waitForEvent("download");
  await asset.getByRole("link", { name: "下载原始资料", exact: true }).click();
  const downloaded = await (await downloading).path();
  if (!downloaded) throw new Error("Missing actual download");
  expect(await readFile(downloaded)).toEqual(original);
  await page.getByRole("button", { name: "预检并执行", exact: true }).click();
  await expect(page.getByText("工程执行成功", { exact: true })).toBeVisible({
    timeout: 30000,
  });
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
      path: evidencePath(`csvw-package-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("csvw-package.json"),
    JSON.stringify(
      {
        task_url: page.url(),
        original_sha256: createHash("sha256").update(original).digest("hex"),
        original_download_equal: true,
        default_standard_recognition: true,
        actual_inspection_run: true,
        task_name_fills: 1,
        file_choices: 1,
        standard_choices: 0,
        datatype_fills: 0,
        identity_fills: 0,
        scope:
          "Declared engineering standard fixture; numerical assessment and export round-trip covered by test_csvw.py",
      },
      null,
      2,
    ),
  );
});
