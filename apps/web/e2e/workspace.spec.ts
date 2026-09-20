import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(12),
});
test("real session, seeded catalog, deep link and logout", async ({ page }) => {
  const credentials = credentialsSchema.parse(
    JSON.parse(
      await readFile(
        new URL("../../../artifacts/runtime/demo-access.json", import.meta.url),
        "utf8",
      ),
    ),
  );
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "当前项目" }),
  ).not.toHaveValue("");
  const readiness = await page.request.get("/health/ready");
  expect(readiness.status()).toBe(200);
  expect((await readiness.json()).dependencies.object_storage).toBe("ready");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "模型中心" })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(8);
  const firstName = await page.locator("tbody tr a").first().innerText();
  await page.locator("tbody tr a").first().click();
  await expect(
    page.getByRole("heading", { name: firstName, exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: firstName, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "数据目录" })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(11);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "场景空间" })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "工作流", exact: true })
    .click();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("heading", { name: "登录工作空间" }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/projects")).status()).toBe(401);
  expect(browserErrors).toEqual([]);
});
