import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("register, revise, export history, copy, enable and import models without self-approving execution", async ({
  page,
}) => {
  test.setTimeout(120000);
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(
        await readFile(
          new URL(
            "../../../artifacts/runtime/demo-access.json",
            import.meta.url,
          ),
          "utf8",
        ),
      ),
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
  await page.goto("/models/new");
  const name = `浏览器模型 ${Date.now()}`;
  await page.getByRole("textbox", { name: "模型名称", exact: true }).fill(name);
  await page.getByRole("textbox", { name: "展示名称", exact: true }).fill(name);
  await page.getByRole("textbox", { name: "许可证", exact: true }).fill("MIT");
  await page
    .getByRole("textbox", { name: "能力（逗号分隔）", exact: true })
    .fill("coastal-demo");
  await page
    .getByRole("group", { name: "空间尺度", exact: true })
    .getByRole("textbox", { name: "单位", exact: true })
    .fill("m");
  await page
    .getByRole("group", { name: "时间尺度", exact: true })
    .getByRole("textbox", { name: "单位", exact: true })
    .fill("s");
  await page.getByRole("button", { name: "添加参数", exact: true }).click();
  const parameter = page.getByRole("group", { name: "参数 1", exact: true });
  await parameter
    .getByRole("textbox", { name: "名称", exact: true })
    .fill("threshold");
  await parameter.getByRole("textbox", { name: "单位", exact: true }).fill("m");
  await parameter
    .getByRole("combobox", { name: "默认值类型", exact: true })
    .selectOption("number");
  await parameter
    .getByRole("spinbutton", { name: "默认值", exact: true })
    .fill("0");
  const createdEvent = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/models") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存模型版本", exact: true }).click();
  const created = await createdEvent;
  expect(created.status()).toBe(201);
  const original = (await created.json()).spec;
  expect(original.execution_status).toBe("NOT_EXECUTABLE");
  expect(original.parameters[0].default).toBe(0);
  await expect(
    page.getByRole("heading", { name: "模型版本管理", exact: true }),
  ).toBeVisible();
  await page.goto("/models");
  await page
    .getByRole("textbox", { name: "搜索全部模型", exact: true })
    .fill(name);
  await page
    .getByRole("textbox", { name: "所需能力", exact: true })
    .fill("coastal-demo");
  await page.getByRole("button", { name: "搜索模型", exact: true }).click();
  await expect(page.getByRole("row").filter({ hasText: name })).toHaveCount(1);
  await expect(
    page.locator(`a[href="/models/${encodeURIComponent(original.id)}"]`),
  ).toBeVisible();
  await page.goto(`/models/${encodeURIComponent(original.id)}/edit`);
  await page
    .getByRole("textbox", { name: "展示名称", exact: true })
    .fill(name + " 修订");
  const revisionEvent = page.waitForResponse(
    (response) =>
      response.url().endsWith(encodeURIComponent(original.id)) &&
      response.request().method() === "PUT",
  );
  await page.getByRole("button", { name: "保存模型版本", exact: true }).click();
  const revision = await revisionEvent;
  expect(revision.status()).toBe(200);
  expect((await revision.json()).spec.version).toBe(2);
  const history = page.getByRole("combobox", {
    name: "查看模型版本",
    exact: true,
  });
  await expect(history.locator('option[value="1"]')).toHaveCount(1);
  await history.selectOption("1");
  await expect(
    page.getByRole("textbox", { name: "展示名称", exact: true }),
  ).toHaveValue(name);
  await expect(
    page.getByRole("button", { name: "保存模型版本", exact: true }),
  ).toBeDisabled();
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "导出此版本 JSON", exact: true })
    .click();
  const content = await readFile((await (await downloadEvent).path())!, "utf8");
  expect(JSON.parse(content).version).toBe(1);
  expect(JSON.parse(content).display_name).toBe(name);
  expect(JSON.parse(content).parameters[0].default).toBe(0);
  await history.selectOption("0");
  await expect(
    page.getByRole("textbox", { name: "展示名称", exact: true }),
  ).toHaveValue(name + " 修订");
  await page
    .getByRole("textbox", { name: "复制模型名称", exact: true })
    .fill(name + " 副本");
  await page.getByRole("button", { name: "复制最新模型", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "展示名称", exact: true }),
  ).toHaveValue(name + " 副本");
  await page.getByRole("button", { name: "停用模型", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "启用模型", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "启用模型", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "停用模型", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("不可执行", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/model-editor.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "归档模型", exact: true }).click();
  await expect(page).toHaveURL(/\/models$/);
  await page.goto("/models/new");
  await page
    .getByLabel("导入 JSON / YAML 模型文件", { exact: true })
    .setInputFiles({
      name: "historical.json",
      mimeType: "application/json",
      buffer: Buffer.from(content),
    });
  await expect(
    page.getByRole("heading", { name: "模型版本管理", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "展示名称", exact: true }),
  ).toHaveValue(name);
  await page.getByRole("button", { name: "归档模型", exact: true }).click();
  await expect(page).toHaveURL(/\/models$/);
  await page.goto(`/models/${encodeURIComponent(original.id)}/edit`);
  await expect(
    page.getByRole("textbox", { name: "展示名称", exact: true }),
  ).toHaveValue(name + " 修订");
  await page.getByRole("button", { name: "归档模型", exact: true }).click();
  await expect(page).toHaveURL(/\/models$/);
  expect(errors).toEqual([]);
});
