import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("stakeholder proposal preserves versions, opinions and hard conflicts", async ({
  page,
}) => {
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8")),
    );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  test.setTimeout(150000);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "工作流", exact: true })
    .click();
  await page
    .getByRole("link", { name: "coastal_impact", exact: true })
    .first()
    .click();
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await page
    .getByRole("link", { name: "查看不可变结果" })
    .click({ timeout: 90000 });
  const resultId = decodeURIComponent(
    new URL(page.url()).pathname.split("/").at(-1)!,
  );
  const response = await page.request.get(
    `/api/v1/results/${encodeURIComponent(resultId)}/content`,
  );
  expect(response.status()).toBe(200);
  const actual = await response.json();
  expect(actual.outputs["statistics.statistics"].inundated_area_m2).toBe(80000);
  expect(
    actual.outputs["statistics.statistics"].estimated_affected_population,
  ).toBe(320);
  const sourceScene = actual.run_manifest.scene;
  await page.getByRole("link", { name: "协同方案", exact: true }).click();
  await page.getByRole("button", { name: "新建方案", exact: true }).click();
  const name = `SYNTHETIC 协同 ${Date.now()}`;
  await page.getByLabel("方案名称", { exact: true }).fill(name);
  await page
    .getByLabel("依据与意见", { exact: true })
    .fill("Synthetic stakeholder proposal; no automatic policy decision.");
  const scenes = page.getByRole("combobox", { name: "固定场景", exact: true });
  await expect
    .poll(async () => scenes.locator("option").count())
    .toBeGreaterThan(1);
  await scenes.selectOption(
    JSON.stringify([sourceScene.id, sourceScene.version]),
  );
  await page
    .getByLabel("已有结果编号（可选，逗号分隔）", { exact: true })
    .fill(resultId);
  await page.getByRole("button", { name: "添加目标", exact: true }).click();
  await page.getByLabel("目标名称 1", { exact: true }).fill("Habitat");
  await page.getByLabel("目标标识 1", { exact: true }).fill("habitat");
  await page.getByLabel("目标权重 1", { exact: true }).fill("1");
  await page.getByRole("button", { name: "添加硬约束", exact: true }).click();
  await page.getByLabel("约束指标 1", { exact: true }).fill("area");
  await page.getByLabel("约束单位 1", { exact: true }).fill("m^2");
  await page.getByLabel("约束下界 1", { exact: true }).fill("100");
  await page.getByRole("button", { name: "保存方案版本", exact: true }).click();
  await expect(page.getByText("当前版本：v1", { exact: true })).toBeVisible();
  await page
    .getByLabel("新增意见", { exact: true })
    .fill("Recorded human opinion");
  await page.getByRole("button", { name: "记录意见", exact: true }).click();
  await expect(
    page.getByText("Recorded human opinion", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑为新版本", exact: true }).click();
  await page.getByLabel("约束下界 1", { exact: true }).fill("");
  await page.getByLabel("约束上界 1", { exact: true }).fill("50");
  await page.getByRole("button", { name: "保存方案版本", exact: true }).click();
  await expect(page.getByText("当前版本：v2", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "与上一版本比较", exact: true })
    .click();
  await expect(page.getByText("EMPTY_INTERVAL", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "提交人工审核", exact: true }).click();
  await expect(page.getByText("当前版本：v3", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "查看 v1", exact: true }).click();
  await expect(
    page.getByText("历史版本：v1（只读）", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Recorded human opinion", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/collaboration.png",
    fullPage: true,
  });
});
