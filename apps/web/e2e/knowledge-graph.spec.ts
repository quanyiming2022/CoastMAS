import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("knowledge graph explores real model data and candidate downstream evidence", async ({
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
    .getByRole("link", { name: "知识图谱", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "模型知识图谱", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "中心节点", exact: true })
    .selectOption({ label: "模型 · Sea-level terrain screening · v1" });
  const canvas = page.getByLabel("知识图谱交互画布", { exact: true });
  await expect(
    canvas
      .locator(".react-flow__node")
      .filter({ hasText: "模型 · Sea-level terrain screening" }),
  ).toBeVisible();
  await expect(
    canvas
      .locator(".react-flow__node")
      .filter({ hasText: "数据资产 · dem.tif" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "关系类型", exact: true })
    .selectOption("CAN_FOLLOW");
  await expect(
    page.getByRole("table").getByText("契约候选，仍需预检").first(),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "关系类型", exact: true })
    .selectOption("");
  await page
    .getByRole("combobox", { name: "邻域深度", exact: true })
    .selectOption("0");
  await expect(canvas.locator(".react-flow__node")).toHaveCount(1);
  await page
    .getByRole("combobox", { name: "邻域深度", exact: true })
    .selectOption("2");
  await expect(
    canvas
      .locator(".react-flow__node")
      .filter({ hasText: "数据资产 · dem.tif" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/knowledge-graph.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "打开来源资源", exact: true }).click();
  await expect(page).toHaveURL(/\/models\//);
  await expect(
    page.getByRole("heading", {
      name: "Sea-level terrain screening",
      exact: true,
    }),
  ).toBeVisible();
});
