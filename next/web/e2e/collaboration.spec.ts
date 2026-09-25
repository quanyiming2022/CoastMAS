import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { actualComparison } from "./comparison-fixtures";
import { evidenceDirectory, evidencePath } from "./evidence";

test("opinions survive immediate navigation and review stays bound to its immutable run", async ({
  page,
}) => {
  const file = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!file) throw new Error("Isolated account required");
  const access = JSON.parse(await readFile(file, "utf8"));
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  const auth = await (await page.request.get("/api/session")).json();
  const headers = { "X-CSRF-Token": auth.csrf };
  const actual = await actualComparison(
    page.request,
    access.project_id,
    headers,
    "协同版本工程验证 " + Date.now(),
  );
  await page.goto(`/tasks/${actual.task}`);
  const panel = page.getByRole("region", {
    name: "协同意见与技术审核",
    exact: true,
  });
  await expect(
    panel.getByText("审核状态：尚未审核", { exact: false }),
  ).toBeVisible();
  const opinion = page.getByLabel("意见内容", { exact: true });
  await opinion.fill("关闭前应保留的最后输入：核对原始日历与单位。");
  // Deliberately leave without waiting for the debounce or clicking save.
  await page.getByRole("link", { name: "← 科研任务", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  await page.goBack();
  await expect(opinion).toHaveValue(
    "关闭前应保留的最后输入：核对原始日历与单位。",
  );
  await page
    .getByLabel("讨论视角（发布意见时必选，不改变权限）", { exact: true })
    .selectOption("research");
  await expect(
    panel.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  await page.reload();
  await expect(opinion).toHaveValue(
    "关闭前应保留的最后输入：核对原始日历与单位。",
  );
  await panel.getByRole("button", { name: "发布意见", exact: true }).click();
  await expect(
    panel.getByText("关闭前应保留的最后输入：核对原始日历与单位。", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(opinion).toHaveValue("");
  await opinion.fill("技术检查通过；不构成业务结论或政策批准。");
  await panel
    .getByRole("button", { name: "记录技术核对通过", exact: true })
    .click();
  await expect(
    panel.getByText("审核状态：技术核对通过", { exact: false }),
  ).toBeVisible();
  const original = await (
    await page.request.get(`/api/jobs/${actual.job}/result`)
  ).json();
  expect(original.states.business_validated).toBe(false);
  const reviews = await (
    await page.request.get(`/api/jobs/${actual.job}/discussion/reviews`)
  ).json();
  expect(reviews.total).toBe(1);
  await page.mouse.move(0, 0);
  await expect(
    panel.getByRole("button", { name: "发布意见", exact: true }),
  ).toHaveCSS("background-color", "rgb(8, 127, 133)");
  await expect(
    panel.getByRole("button", { name: "记录技术核对通过", exact: true }),
  ).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    await panel.scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 1);
    await panel.screenshot({
      path: evidencePath(`collaboration-${width}.png`),
    });
  }
  await writeFile(
    evidencePath("collaboration.json"),
    JSON.stringify(
      {
        task_id: actual.task,
        job_id: actual.job,
        opinion_restored_after_immediate_navigation: true,
        opinion_restored_after_refresh: true,
        review_count: reviews.total,
        business_validated: original.states.business_validated,
        isolated_fixture_only: true,
        measured_input: {
          scope:
            "discussion only; actual comparison prepared separately through normal APIs and worker",
          manual_fills: 2,
          selections: 1,
          confirmations: 0,
          duplicate_fills: 0,
          recovery_retyped: 0,
        },
      },
      null,
      2,
    ),
  );
});
