import { evidenceDirectory, evidencePath } from "./evidence";
import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";

test("method definition is durable and reused by actual asset-based assessment", async ({
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
  await page.getByRole("link", { name: "方法与依据", exact: true }).click();
  const name = "工程评价方法 " + Date.now();
  await page.getByLabel("方法名称", { exact: true }).fill(name);
  await page.getByRole("button", { name: "建立方法草稿" }).click();
  await expect(
    page.getByRole("heading", { name: "维护评价方法" }),
  ).toBeVisible();
  await page
    .getByLabel("方法依据", { exact: true })
    .fill(
      "独立工程测试：距离0至2000米，方向正向，单指标权重1；不构成真实海岸区科学结论。",
    );
  await page
    .getByRole("combobox", { name: "计算方法", exact: true })
    .selectOption("weighted");
  await page.getByRole("button", { name: "添加指标定义" }).click();
  await page.getByLabel("科学含义", { exact: true }).fill("distance");
  await page.getByLabel("参考单位", { exact: true }).fill("m");
  await page.getByLabel("参考下限", { exact: true }).fill("0");
  await page.getByLabel("参考上限", { exact: true }).fill("2000");
  await page
    .getByRole("combobox", { name: "指标方向", exact: true })
    .selectOption("positive");
  await page.getByLabel("认可权重", { exact: true }).fill("1");
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  const definitionURL = page.url();
  await page.reload();
  await expect(page.getByLabel("参考上限", { exact: true })).toHaveValue(
    "2000",
  );
  const publication = page.waitForResponse(
    (response) =>
      response.url().endsWith("/publish-method") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "发布并认可方法" }).click();
  const published = await publication;
  expect(published.status()).toBe(201);
  const template = (await published.json()).template;
  await page.getByRole("link", { name: "任务目录", exact: true }).click();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("已有资料按认可方法评价");
  await page
    .getByRole("combobox", { name: "任务类型", exact: true })
    .selectOption("assessment");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.getByLabel("添加资料", { exact: true })).toBeVisible();
  await page.getByLabel("添加资料", { exact: true }).setInputFiles({
    name: "method-observations.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,distance\n001,1000\n002,2000\n"),
  });
  await expect(page.getByLabel("用途 table/id")).toBeVisible();
  await page
    .getByRole("combobox", { name: "本次采用的方法", exact: true })
    .selectOption(template.id);
  await page.getByLabel("用途 table/id").selectOption("identity");
  await page.getByLabel("科学含义 table/distance").fill("distance");
  await page.getByLabel("单位 table/distance").fill("m");
  await page.getByLabel("支撑 table/distance").selectOption("point");
  await page.getByRole("button", { name: "预检并执行", exact: true }).click();
  await expect(page.getByText("工程执行成功", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByRole("columnheader", { name: "评价得分" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "观测结果", exact: true })
      .getByRole("cell", { name: "001", exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const path = await (await download).path();
  if (!path) throw new Error("Actual download missing");
  const output = JSON.parse(await readFile(path, "utf8"));
  expect(output.data.scores).toEqual([0.5, 1]);
  expect(output.data.method_snapshot.id).toBe(template.id);
  expect(output.states.business_validated).toBe(false);
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width!);
    await page.screenshot({
      path: evidencePath(`method-result-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("method-assessment.json"),
    JSON.stringify(
      {
        status: "PASS",
        definitionURL,
        taskURL: page.url(),
        template_id: template.id,
        scores: output.data.scores,
        purpose: "engineering verification; not scientific conclusion",
        actions: {
          first_method_text_fills: 8,
          first_method_selections: 2,
          approval_clicks: 1,
          task_text_fills: 3,
          task_selections: 4,
          file_choices: 1,
          execute_clicks: 1,
          internal_json_edits: 0,
          manual_observation_rows: 0,
        },
      },
      null,
      2,
    ),
  );
});
