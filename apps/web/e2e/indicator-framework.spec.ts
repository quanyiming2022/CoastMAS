import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";
test("indicator framework versions prepare real data and produce a temporal evaluation workflow", async ({
  page,
}) => {
  test.setTimeout(150000);
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
  if (
    (await page
      .getByRole("button", { name: "评价与协同", exact: true })
      .getAttribute("aria-expanded")) === "false"
  )
    await page.getByRole("button", { name: "评价与协同", exact: true }).click();
  await page.getByRole("link", { name: "综合评价", exact: true }).click();
  await page.getByRole("link", { name: "新建指标体系", exact: true }).click();
  const name = `SYNTHETIC 评价体系 ${Date.now()}`;
  await page.getByLabel("体系名称", { exact: true }).fill(name);
  await page
    .getByLabel("依据与适用范围", { exact: true })
    .fill("Synthetic acceptance only; not a unique sustainability framework.");
  await page.getByLabel("示范体系（DEMO FRAMEWORK）", { exact: true }).check();
  await page.getByRole("button", { name: "添加指标", exact: true }).click();
  const indicator = page.getByRole("group", { name: "指标 1", exact: true });
  for (const [label, value] of [
    ["指标名称", "Economic"],
    ["分类", "资源利用"],
    ["输出单位", "1"],
    ["参考下界", "0"],
    ["参考上界", "100"],
    ["手工权重", "1"],
    ["公式输入 x 对应的数据列", "economic"],
  ])
    await indicator.getByLabel(label!, { exact: true }).fill(value!);
  await page
    .getByRole("button", { name: "保存指标体系版本", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "指标体系版本管理", exact: true }),
  ).toBeVisible();
  const frameworkUrl = page.url();
  const select = page.getByRole("combobox", { name: "观测数据", exact: true });
  await expect(
    select.locator("option").filter({ hasText: "Synthetic indicator frame C" }),
  ).toHaveCount(1);
  const option = await select
    .locator("option")
    .filter({ hasText: "Synthetic indicator frame C" })
    .getAttribute("value");
  await select.selectOption(option!);
  const imported = page.waitForResponse(
    (r) => r.url().endsWith("/prepare") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "准备固定版本输入", exact: true })
    .click();
  const response = await imported;
  expect(response.status()).toBe(201);
  const prepared = z
    .object({
      resource_id: z.string(),
      spec: z.object({
        checksum: z.string(),
        quality: z.object({ validated: z.literal(true) }),
      }),
    })
    .parse(await response.json());
  const download = await page.request.get(
    `/api/v1/data-assets/${encodeURIComponent(prepared.resource_id)}/download`,
  );
  expect(download.status()).toBe(200);
  const document = z
    .object({
      frame: z.object({ values: z.array(z.array(z.array(z.number()))) }),
      framework: z.object({ version: z.number() }),
      weight_method: z.string(),
    })
    .parse(await download.json());
  expect(document.frame.values[0]?.[0]?.[0]).toBe(20);
  expect(document.framework.version).toBe(1);
  expect(document.weight_method).toBe("manual");
  await page
    .getByRole("combobox", { name: "评价场景", exact: true })
    .selectOption({ label: "Synthetic assessment scenario C · v1" });
  await page.getByRole("button", { name: "生成评价方案", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存评价记录与工作流", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "保存评价记录与工作流", exact: true })
    .click();
  await expect(page).toHaveURL(/\/assessment-records\//);
  const assessmentUrl = page.url();
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByText("固定配置预检通过；提交时服务端会再次检查。", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "提交评价运行", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\//);
  await expect(page.getByText("已成功", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  await page.getByRole("link", { name: "查看不可变结果", exact: true }).click();
  await expect(page).toHaveURL(/\/results\//);
  const resultId = page.url().split("/").at(-1)!;
  const resultResponse = await page.request.get(
    `/api/v1/results/${encodeURIComponent(resultId)}/content`,
  );
  expect(resultResponse.status()).toBe(200);
  const result = z
    .object({
      outputs: z.object({
        "composite.scores": z.object({ values: z.array(z.array(z.number())) }),
        "change.change": z.object({
          change: z.array(z.number()),
          trend: z.array(z.number()),
        }),
      }),
    })
    .parse(await resultResponse.json());
  expect(result.outputs["composite.scores"].values[0]).toEqual([
    0.2, 0.4, 0.6, 0.8,
  ]);
  for (const value of result.outputs["change.change"].change)
    expect(value).toBeCloseTo(0.2, 12);
  for (const value of result.outputs["change.change"].trend)
    expect(value).toBeCloseTo(0.1, 12);
  await page.goto(assessmentUrl);
  await expect(
    page.getByRole("link", { name: "查看评价结果", exact: true }),
  ).toBeVisible();
  await page.goto(frameworkUrl);
  await page.getByLabel("体系名称", { exact: true }).fill(name + " revised");
  await page
    .getByRole("button", { name: "保存指标体系版本", exact: true })
    .click();
  await expect(
    page
      .getByRole("combobox", { name: "查看指标体系版本", exact: true })
      .locator('option[value="2"]'),
  ).toHaveCount(1);
  await page
    .getByRole("combobox", { name: "查看指标体系版本", exact: true })
    .selectOption("1");
  await expect(page.getByLabel("体系名称", { exact: true })).toHaveValue(name);
  await expect(page.getByLabel("体系名称", { exact: true })).toBeDisabled();
  await page.goto(
    `/data/${encodeURIComponent(prepared.resource_id)}/workspace`,
  );
  await expect(
    page.getByRole("heading", { name: "已核实的评价来源", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Synthetic indicator frame C", exact: true })
    .click();
  await expect(
    page.getByRole("combobox", { name: "查看数据版本", exact: true }),
  ).toHaveValue("1");
  await expect(
    page.getByRole("button", { name: "保存数据修订", exact: true }),
  ).toBeDisabled();
  await page.goto(
    `/data/${encodeURIComponent(prepared.resource_id)}/workspace`,
  );
  await page.getByRole("link", { name, exact: true }).click();
  await expect(page.getByLabel("体系名称", { exact: true })).toHaveValue(name);
  await expect(page.getByLabel("体系名称", { exact: true })).toBeDisabled();
  await page.screenshot({
    path: "../../artifacts/screenshots/indicator-framework.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
