import { mkdir, readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

test("temporal form freezes observed support and real worker publishes weighted result", async ({
  page,
}) => {
  test.setTimeout(120000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("link", { name: "时间适配", exact: true }).click();
  const project = await page
    .getByLabel("当前项目", { exact: true })
    .inputValue();
  const scenes = await (
    await page.request.get(`/api/v1/scenes?project_id=${project}`)
  ).json();
  await page
    .getByRole("combobox", { name: "沿用研究区的场景", exact: true })
    .selectOption(scenes[0].id);
  await page.getByLabel("名称", { exact: true }).fill("隔离验证：不等时长温度");
  await page
    .getByLabel("数据来源", { exact: true })
    .fill("SYNTHETIC hand calculated fixture");
  await page.getByLabel("许可证", { exact: true }).fill("CC0");
  await page.getByLabel("物理变量", { exact: true }).fill("air_temperature");
  await page.getByLabel("输入单位", { exact: true }).fill("degC");
  await page.getByLabel("输出单位", { exact: true }).fill("kelvin");
  await page
    .getByLabel("目标开始时间", { exact: true })
    .fill("2025-01-01T00:00:00Z");
  await page
    .getByLabel("目标结束时间", { exact: true })
    .fill("2025-01-01T04:00:00Z");
  await page
    .getByLabel("观测1开始", { exact: true })
    .fill("2025-01-01T00:00:00Z");
  await page
    .getByLabel("观测1结束", { exact: true })
    .fill("2025-01-01T01:00:00Z");
  await page.getByLabel("观测1数值", { exact: true }).fill("10");
  await page.getByRole("button", { name: "添加观测", exact: true }).click();
  await page
    .getByLabel("观测2开始", { exact: true })
    .fill("2025-01-01T01:00:00Z");
  await page
    .getByLabel("观测2结束", { exact: true })
    .fill("2025-01-01T04:00:00Z");
  await page.getByLabel("观测2数值", { exact: true }).fill("20");
  await mkdir("../../artifacts/screenshots", { recursive: true });
  await page.screenshot({
    path: "../../artifacts/screenshots/temporal-form.png",
    fullPage: true,
  });
  const savedResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/adaptations/temporal") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "保存时间适配工作流", exact: true })
    .click();
  const saved = await savedResponse;
  expect(saved.status()).toBe(201);
  const frozen = await saved.json();
  await expect(
    page.getByRole("combobox", { name: "运行场景", exact: true }),
  ).toHaveValue(frozen.scene.id);
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await expect(page.getByText("已成功", { exact: true }).first()).toBeVisible({
    timeout: 60000,
  });
  const id = new URL(page.url()).pathname.split("/").at(-1)!;
  const results = await (
    await page.request.get(`/api/v1/results?project_id=${project}`)
  ).json();
  const published = results.find(
    (row: { job_id: string }) => row.job_id === id,
  );
  expect(published).toBeTruthy();
  const result = await (
    await page.request.get(`/api/v1/results/${published.id}/content`)
  ).json();
  expect(result.outputs["adapt.result"].value).toBeCloseTo(290.65, 10);
  expect(result.outputs["adapt.result"].method).toBe("mean");
  expect(result.outputs["adapt.result"].unit).toBe("kelvin");
  expect(result.llm_calls).toBe(0);
  await page.getByRole("link", { name: "查看不可变结果", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "时间适配结果", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("temporal-value")).toHaveText("290.65 kelvin");
  await expect(
    page.getByRole("heading", { name: "时间适配结果", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  await page.screenshot({
    path: "../../artifacts/screenshots/temporal-result.png",
    fullPage: true,
  });
});
