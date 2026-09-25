import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { evidenceDirectory, evidencePath } from "./evidence";

test("CF time task reads defaults, keeps 360-day dates and completes with only target dates", async ({
  page,
}) => {
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Isolated test account required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("CF 360日历工程验证 " + Date.now());
  await page
    .getByRole("combobox", { name: "任务类型", exact: true })
    .selectOption("temporal");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await page
    .getByLabel("添加资料", { exact: true })
    .setInputFiles(
      fileURLToPath(new URL("./fixtures/temporal-360day.nc", import.meta.url)),
    );
  await expect(
    page.getByRole("combobox", { name: "观测变量", exact: true }),
  ).toHaveValue("height");
  await expect(
    page.getByRole("combobox", { name: "目标方法", exact: true }),
  ).toHaveValue("mean");
  await expect(page.getByLabel("输出单位", { exact: true })).toHaveValue("m");
  await page
    .getByLabel("开始日期（源日历）", { exact: true })
    .fill("2022-02-29");
  await page
    .getByLabel("结束日期（不包含）", { exact: true })
    .fill("2022-03-02");
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByLabel("开始日期（源日历）", { exact: true }),
  ).toHaveValue("2022-02-29");
  const submitted = page.waitForResponse(
    (r) => r.url().endsWith("/execute") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "预检并执行", exact: true }).click();
  const reply = await submitted;
  expect(reply.status()).toBe(202);
  const job = await reply.json();
  await expect(page.getByText("2 m", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await expect(
    page.getByText("实际覆盖 3 days · 使用 3 条观测", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "时间适配成果", exact: true })
      .getByText("360_day", { exact: true }),
  ).toBeVisible();
  const downloading = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const downloaded = await (await downloading).path();
  if (!downloaded) throw new Error("Missing actual download");
  const result = JSON.parse(await readFile(downloaded, "utf8"));
  expect(result.data.value).toBe(2);
  expect(result.data.calendar).toBe("360_day");
  expect(result.data.start).toBe("2022-02-29");
  expect(result.manifest.draft.options.temporal_automatic.file_choices).toEqual(
    { variable: "height", method: "mean", output_unit: "m" },
  );
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
      path: evidencePath(`temporal-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("temporal-task.json"),
    JSON.stringify(
      {
        task_url: page.url(),
        job_id: job.id,
        actual_value: 2,
        unit: "m",
        calendar: "360_day",
        saved_target_restored: true,
        measured_input: {
          scope: "after login through downloaded result",
          manual_fills: 3,
          selections: 2,
          confirmations: 0,
          duplicate_fills: 0,
          cross_page_trips: 0,
          notes:
            "任务名称与两个日期共3次填写；任务目的和文件共2次选择。变量、方法、单位均由文件自动带入。",
        },
        engineering_fixture_only: true,
      },
      null,
      2,
    ),
  );
});
