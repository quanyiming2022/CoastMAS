import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("historical runs retain frozen results without reverting the current draft", async ({
  page,
}) => {
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByLabel("任务名称", { exact: true }).fill("第一份固定任务");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await page.getByLabel("添加资料", { exact: true }).setInputFiles({
    name: "history.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("id,value\n001,0\n002,2\n"),
  });
  await expect(
    page
      .getByRole("navigation", { name: "任务资料列表" })
      .getByRole("button", { name: "history.csv", exact: true }),
  ).toBeVisible();
  async function execute() {
    const queued = page.waitForResponse(
      (r) => r.url().endsWith("/execute") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "预检并执行", exact: true }).click();
    const reply = await queued;
    expect(reply.status()).toBe(202);
    const job = await reply.json();
    await expect(
      page.getByRole("link", { name: "下载完整成果", exact: true }),
    ).toHaveAttribute("href", `/api/jobs/${job.id}/download`, {
      timeout: 30000,
    });
    return job;
  }
  const first = await execute();
  await page.getByLabel("任务名称", { exact: true }).fill("第二份当前草稿");
  const second = await execute();
  expect(second.manifest.draft_revision).toBeGreaterThan(
    first.manifest.draft_revision,
  );
  await page.getByText("全部运行记录（2 次）", { exact: true }).click();
  const table = page.getByRole("table", { name: "任务运行历史" });
  await table
    .getByRole("button", {
      name: new RegExp(`查看任务版本 ${first.manifest.draft_revision} 的运行`),
    })
    .click();
  await expect(
    page.getByRole("link", { name: "下载完整成果", exact: true }),
  ).toHaveAttribute("href", `/api/jobs/${first.id}/download`);
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "第二份当前草稿",
  );
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整成果", exact: true }).click();
  const path = await (await download).path();
  if (!path) throw new Error("Missing real historical output");
  const old = JSON.parse(await readFile(path, "utf8"));
  expect(old.manifest.draft.title).toBe("第一份固定任务");
  expect(old.data.datasets[0].facts.layers[0].row_count).toBe(2);
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 1);
    await page.screenshot({
      path: evidencePath(`run-history-${width}.png`),
      fullPage: true,
    });
  }
  await writeFile(
    evidencePath("run-history.json"),
    JSON.stringify(
      {
        task_url: page.url(),
        first_run: first.id,
        second_run: second.id,
        immutable_first_revision: first.manifest.draft_revision,
        current_revision: second.manifest.draft_revision,
        historical_download_verified: true,
        draft_reverted: false,
      },
      null,
      2,
    ),
  );
});
