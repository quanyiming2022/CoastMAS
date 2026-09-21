import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";
test("upload real data, preview zero, revise, revalidate and download immutable history", async ({
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
  await page.goto("/data/new");
  const name = `浏览器数据 ${Date.now()}`;
  const content = "height,label\n0,zero\n2,two\n";
  await page.getByLabel("数据文件", { exact: true }).setInputFiles({
    name: "zero.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(content),
  });
  await page.getByRole("textbox", { name: "数据名称", exact: true }).fill(name);
  await page
    .getByRole("textbox", { name: "数据来源", exact: true })
    .fill("SYNTHETIC browser validation");
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
  const upload = page.waitForResponse(
    (r) =>
      r.url().endsWith("/data-assets/upload") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "上传并检查数据", exact: true })
    .click();
  const uploaded = await upload;
  expect(uploaded.status()).toBe(201);
  const first = (await uploaded.json()).spec;
  expect(first.quality.validated).toBe(true);
  expect(first.quality.row_count).toBe(2);
  await expect(
    page.getByRole("heading", { name: "数据版本管理", exact: true }),
  ).toBeVisible();
  await page.goto("/data");
  await page
    .getByRole("textbox", { name: "搜索全部数据", exact: true })
    .fill(name);
  await page
    .getByRole("combobox", { name: "文件格式筛选", exact: true })
    .selectOption("CSV");
  await page
    .getByRole("combobox", { name: "数据类别筛选", exact: true })
    .selectOption("table");
  await page.getByRole("button", { name: "搜索数据", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await page.getByRole("link", { name, exact: true }).click();
  await page
    .getByRole("link", { name: "管理数据版本与预览", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "数据名称", exact: true }),
  ).toHaveValue(name);
  await page
    .getByRole("button", { name: "读取实际文件预览", exact: true })
    .click();
  await expect(
    page.getByRole("table", { name: "数据预览行" }).getByRole("row"),
  ).toHaveCount(3);
  await expect(
    page
      .getByRole("table", { name: "数据预览行" })
      .getByRole("cell", { name: '"0"', exact: true }),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: "数据名称", exact: true })
    .fill(name + " 修订");
  await page.getByRole("button", { name: "保存数据修订", exact: true }).click();
  await expect(page.getByText("未验证", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "重新检查并保存质量版本", exact: true })
    .click();
  await expect(page.getByText("已验证", { exact: true })).toBeVisible();
  const history = page.getByRole("combobox", {
    name: "查看数据版本",
    exact: true,
  });
  await expect(history.locator('option[value="3"]')).toHaveCount(1);
  await history.selectOption("1");
  await expect(
    page.getByRole("textbox", { name: "数据名称", exact: true }),
  ).toHaveValue(name);
  await expect(
    page.getByRole("button", { name: "保存数据修订", exact: true }),
  ).toBeDisabled();
  const download = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "下载此版本原始文件", exact: true })
    .click();
  expect(await readFile((await (await download).path())!, "utf8")).toBe(
    content,
  );
  await page
    .getByRole("button", { name: "读取实际文件预览", exact: true })
    .click();
  await expect(page.getByRole("table", { name: "数据预览行" })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/data-workspace.png",
    fullPage: true,
  });
  await history.selectOption("0");
  await page.getByRole("button", { name: "归档数据", exact: true }).click();
  await expect(page).toHaveURL(/\/data$/);
  expect(errors).toEqual([]);
});
