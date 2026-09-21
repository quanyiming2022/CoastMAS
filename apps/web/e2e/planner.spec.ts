import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";
test("deterministic planning resolves explicit data ambiguity without external calls", async ({
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
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "智能编排", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "规划场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page
    .getByLabel("管理目标", { exact: true })
    .fill("海岸影响筛查：海平面上升0.5米");
  await page.getByRole("button", { name: "生成规划", exact: true }).click();
  await expect(page.getByText("DATA_AMBIGUOUS", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "保存工作流", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "overlay.land_cover 的数据", exact: true })
    .selectOption({ label: "land_cover_t1.tif · v1" });
  await page.getByRole("button", { name: "生成规划", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存工作流", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByText("已预留外部请求：0 / 2", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "刷新调用账本", exact: true }).click();
  await expect(
    page.getByText("没有外部调用记录。", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "保存工作流", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "coastal_impact", exact: true }),
  ).toBeVisible();
});
