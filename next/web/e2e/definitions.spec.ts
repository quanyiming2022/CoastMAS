import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("new bytes inherit an approved scoped dictionary without repeating scientific fields", async ({
  page,
}) => {
  test.setTimeout(90000);
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!accessFile) throw new Error("Explicit isolated access file required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const name = "definition-" + Date.now() + ".csv";
  async function create(title: string, bytes: string) {
    await expect(
      page.getByRole("heading", { name: "科研任务", exact: true }),
    ).toBeVisible();
    await page.getByLabel("任务名称", { exact: true }).fill(title);
    await page.getByRole("button", { name: "开始任务", exact: true }).click();
    await page.getByLabel("添加资料", { exact: true }).setInputFiles({
      name,
      mimeType: "text/csv",
      buffer: Buffer.from(bytes),
    });
    await expect(
      page
        .getByRole("navigation", { name: "任务资料列表" })
        .getByRole("button", { name: name, exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("添加资料", { exact: true })).toBeEnabled();
  }
  await create(
    "首次填写工程指标定义",
    "id,distance\n01,0\n02," + Date.now() + "\n",
  );
  const concept = page.getByRole("textbox", {
    name: /^科学含义 .*\/distance$/,
  });
  const unit = page.getByRole("textbox", { name: /^单位 .*\/distance$/ });
  await concept.fill("distance_to_water");
  await unit.fill("m");
  await page.getByText("将已知指标定义保存为项目依据", { exact: true }).click();
  await page
    .getByRole("combobox", { name: "定义适用范围", exact: true })
    .selectOption("same_names");
  await page
    .getByLabel("指标定义依据", { exact: true })
    .fill("工程测试采集规范；只验证复用机制");
  const published = page.waitForResponse(
    (response) =>
      response.url().endsWith("/publish-definition") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "保存并认可指标定义", exact: true })
    .click();
  const firstResponse = await published;
  expect(firstResponse.status()).toBe(201);
  const first = await firstResponse.json();
  await expect(page.getByText("认可模板 v1", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "任务目录", exact: true }).click();
  await create(
    "新批次零重复科学填写",
    "id,distance\n03,17\n04," + Date.now() + "\n",
  );
  await expect(concept).toHaveValue("distance_to_water");
  await expect(unit).toHaveValue("m");
  const taskID = new URL(page.url()).pathname.split("/").at(-1);
  const task = await (await page.request.get("/api/tasks/" + taskID)).json();
  expect(task.draft.selection[0].asset_id).not.toBe(
    first.task.draft.selection[0].asset_id,
  );
  expect(
    task.draft.mapping.find((entry: { field: string }) =>
      entry.field.endsWith("/distance"),
    ).template_id,
  ).toBe(first.template.id);
  expect(task.draft.mapping[0].unit).toBeNull();
  expect(
    task.draft.options.inherited_declarations[task.draft.selection[0].asset_id],
  ).toEqual({});
  await page.reload();
  await expect(unit).toHaveValue("m");
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
      path: evidencePath(`definition-reuse-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("definition-reuse.json"),
    JSON.stringify(
      {
        first_task: first.task.id,
        new_batch_task: taskID,
        definition: first.template.id,
        distinct_assets: true,
        first_scientific_text_fills: 3,
        scope_selections: 1,
        publication_confirmations: 1,
        new_batch_scientific_fills: 0,
        new_batch_definition_confirmations: 0,
        refresh_retyped_fields: 0,
        engine_execution: "inspection",
        formal_business_result: false,
        scope:
          "Browser-entered engineering dictionary; no supplied coastal scientific meanings assumed",
      },
      null,
      2,
    ),
  );
});
