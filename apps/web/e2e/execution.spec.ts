import { mkdir, readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("browser preflight -> Redis worker -> immutable coastal result", async ({
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
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await mkdir(new URL("../../../artifacts/screenshots/", import.meta.url), {
    recursive: true,
  });
  await page.screenshot({
    path: "../../artifacts/screenshots/dashboard.png",
    fullPage: true,
  });
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "工作流", exact: true })
    .click();
  // Names are not unique; pin the chosen identity and verify it in the downloaded manifest.
  const workflowLink = page
    .getByRole("link", { name: "coastal_impact", exact: true })
    .first();
  const workflowHref = await workflowLink.getAttribute("href");
  expect(workflowHref).toMatch(/^\/workflows\/plan%3A[0-9a-f]{64}$/);
  const selectedWorkflowId = decodeURIComponent(
    workflowHref!.slice("/workflows/".length),
  );
  await workflowLink.click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await expect(page.locator(".react-flow__node")).toHaveCount(10);
  await page.screenshot({
    path: "../../artifacts/screenshots/workflow.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await expect(page.getByRole("heading", { name: "任务详情" })).toBeVisible();
  await page
    .getByRole("link", { name: "查看不可变结果" })
    .click({ timeout: 90000 });
  await expect(
    page.getByRole("heading", { name: "结果与科研追溯" }),
  ).toBeVisible();
  await expect(page.getByText("80000", { exact: true })).toBeVisible();
  await expect(page.getByText("320", { exact: true })).toBeVisible();
  await expect(page.locator(".geographic-map")).toHaveAttribute(
    "data-loaded",
    "true",
  );
  await expect(
    page.getByRole("img", { name: "估算受影响人口，单位：人" }),
  ).toBeVisible();
  await expect(
    page.getByText("本结果为地形连通筛查，不是水动力模拟。", { exact: false }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整结果" }).click();
  const download = await downloadPromise;
  const outputFile = await download.path();
  expect(outputFile).not.toBeNull();
  const output = JSON.parse(await readFile(outputFile!, "utf8"));
  expect(output.outputs["statistics.statistics"].inundated_area_m2).toBe(80000);
  expect(
    output.outputs["statistics.statistics"].estimated_affected_population,
  ).toBe(320);
  expect(output.executed_nodes).toEqual(["screening", "overlay", "statistics"]);
  expect(output.llm_calls).toBe(0);
  expect(output.run_manifest.workflow.id).toBe(selectedWorkflowId);
  await page.screenshot({
    path: "../../artifacts/screenshots/coastal-result.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("button", { name: "退出登录" })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/coastal-result-mobile.png",
    fullPage: true,
  });
  expect(browserErrors).toEqual([]);
});
