import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";
test("registered HTTP source imports real immutable bytes with historical lineage", async ({
  page,
}) => {
  test.setTimeout(120000);
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8")),
    );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await page.goto("/data-sources/new");
  const name = `HTTP 验收数据源 ${Date.now()}`;
  await page
    .getByRole("textbox", { name: "数据源名称", exact: true })
    .fill(name);
  const selector = page.getByRole("combobox", {
    name: "已批准的连接器",
    exact: true,
  });
  await expect(selector.locator('option[value="demo-csv"]')).toHaveCount(1);
  await selector.selectOption("demo-csv");
  await page
    .getByRole("textbox", { name: "数据名称", exact: true })
    .fill(name + " 快照");
  await page
    .getByRole("textbox", { name: "数据来源", exact: true })
    .fill("SYNTHETIC HTTP acceptance fixture");
  await page.getByRole("textbox", { name: "许可证", exact: true }).fill("CC0");
  await page.getByRole("button", { name: "添加数据变量", exact: true }).click();
  const variable = page.getByRole("group", { name: "数据变量 1", exact: true });
  for (const [label, value] of [
    ["名称", "height"],
    ["标准变量名", "elevation"],
    ["说明", "Synthetic height"],
    ["单位", "m"],
    ["量纲", "[length]"],
    ["空间支撑", "point"],
    ["时间支撑", "instant"],
  ])
    await variable
      .getByRole("textbox", { name: label, exact: true })
      .fill(value!);
  for (const [label, value] of [
    ["数据类型", "array"],
    ["语义类型", "continuous"],
    ["聚合语义", "intensive"],
    ["缺失值策略", "reject"],
  ])
    await variable
      .getByRole("combobox", { name: label, exact: true })
      .selectOption(value!);
  await page
    .getByRole("button", { name: "保存数据源版本", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "数据源版本管理", exact: true }),
  ).toBeVisible();
  async function importSnapshot() {
    const response = page.waitForResponse(
      (r) => r.url().endsWith("/snapshots") && r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "导入文件快照", exact: true })
      .click();
    const received = await response;
    expect(received.status()).toBe(201);
    return (await received.json()).resource_id as string;
  }
  const assetId = await importSnapshot();
  expect(await importSnapshot()).toBe(assetId);
  await page.getByRole("link", { name: "查看已导入数据", exact: true }).click();
  await page
    .getByRole("button", { name: "读取实际文件预览", exact: true })
    .click();
  await expect(
    page
      .getByRole("table", { name: "数据预览行" })
      .getByRole("cell", { name: '"0"', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("固定来源版本 1", { exact: false }),
  ).toBeVisible();
  await page.getByRole("link", { name, exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存数据源版本", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "查看数据源版本", exact: true })
    .selectOption("0");
  await page
    .getByRole("textbox", { name: "数据源名称", exact: true })
    .fill(name + " 修订");
  await page
    .getByRole("button", { name: "保存数据源版本", exact: true })
    .click();
  await expect(
    page
      .getByRole("combobox", { name: "查看数据源版本", exact: true })
      .locator('option[value="2"]'),
  ).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "查看已导入数据", exact: true }),
  ).toHaveCount(0);
  await page.goto(`/data/${encodeURIComponent(assetId)}/workspace`);
  await page.getByRole("link", { name, exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "数据源名称", exact: true }),
  ).toHaveValue(name);
  await page
    .getByRole("combobox", { name: "查看数据源版本", exact: true })
    .selectOption("0");
  await page.screenshot({
    path: "../../artifacts/screenshots/data-source.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "归档数据源", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("DEPENDENCY_CONFLICT");
  expect(errors).toEqual([]);
});
