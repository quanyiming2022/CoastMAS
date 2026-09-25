import { mkdir, readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

test("business intake reads local source evidence without uploading research data", async ({
  page,
}) => {
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await page.goto("/data");
  await page.getByRole("link", { name: "业务资料检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "业务资料检查", exact: true }),
  ).toBeVisible();
  const writes: string[] = [];
  page.on("request", (request) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method()))
      writes.push(request.url());
  });
  const path = process.env.COASTMAS_BUSINESS_REPORT;
  if (!path)
    throw new Error(
      "COASTMAS_BUSINESS_REPORT is required for actual source verification",
    );
  await page.getByLabel("选择业务资料检查报告").setInputFiles(path);
  await expect(
    page.getByText("数据年份：2022（不等于连续全年观测覆盖）"),
  ).toBeVisible();
  await page.getByLabel("筛选全部栅格").fill("TN/");
  await expect(page.getByText(/经纬度坐标超出合法范围/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "投影寻踪聚类 GPL-3", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "投影寻踪回归 MIT", exact: true })).toBeVisible();
  await mkdir("../../artifacts/business-intake", { recursive: true });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(viewport.width + 1);
    await page.screenshot({
      path: `../../artifacts/business-intake/tn-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.getByLabel("筛选全部栅格").fill("zhusanjiao/");
  await expect(page.getByText("用户声明单位：m")).toHaveCount(4);
  await expect(page.getByText(/第1波段采样/)).toHaveCount(4);
  await expect(page.getByText("超过当前网页 64 MiB 上传上限")).toHaveCount(4);
  await page.screenshot({
    path: "../../artifacts/business-intake/prd-390.png",
    fullPage: true,
  });
  await page.getByLabel("筛选全部栅格").fill("");
  await page.getByRole("button", { name: "下一页栅格" }).click();
  await expect(page.getByText("共 40 份 · 第 2 页")).toBeVisible();
  await page
    .getByLabel("选择业务资料检查报告")
    .setInputFiles({
      name: "invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from("{}"),
    });
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page.getByRole("table", { name: "业务栅格检查" })).toHaveCount(
    0,
  );
  expect(writes).toEqual([]);
});
