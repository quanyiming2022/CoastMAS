import { test, expect, type Page } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("two editors resolve a real server conflict; lost acknowledgment never duplicates a revision", async ({
  page,
  browser,
}) => {
  test.setTimeout(90000);
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!accessFile) throw new Error("Explicit isolated access file required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  async function login(target: Page) {
    await target.goto("/?project=" + access.project_id);
    await target.getByLabel("邮箱", { exact: true }).fill(access.email);
    await target.getByLabel("密码", { exact: true }).fill(access.password);
    await target.getByRole("button", { name: "登录", exact: true }).click();
    await expect(
      target.getByRole("heading", { name: "科研任务", exact: true }),
    ).toBeVisible();
  }
  const saved = (target: Page) =>
    target.getByRole("status").filter({ hasText: "已保存到服务器" });
  await login(page);
  await page.getByLabel("任务名称", { exact: true }).fill("并发编辑原稿");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  const taskURL = page.url();
  const taskID = new URL(taskURL).pathname.split("/").at(-1);
  const apiPath = "/api/tasks/" + taskID;
  const context = await browser.newContext();
  const second = await context.newPage();
  try {
    await login(second);
    await second.goto(taskURL);
    await expect(second.getByLabel("任务名称", { exact: true })).toHaveValue(
      "并发编辑原稿",
    );
    await page
      .getByLabel("任务名称", { exact: true })
      .fill("窗口一已保存的标题");
    await expect(saved(page)).toBeVisible();
    await second
      .getByLabel("任务名称", { exact: true })
      .fill("窗口二需要保留的标题");
    const panel = second.getByRole("region", { name: "处理并发修改" });
    await expect(panel).toBeVisible();
    await expect(
      panel.getByText("窗口一已保存的标题", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByText("窗口二需要保留的标题", { exact: true }),
    ).toBeVisible();
    await expect(
      panel.getByRole("button", { name: "采用选择并继续保存" }),
    ).toBeDisabled();
    await mkdir(evidenceDirectory, { recursive: true });
    for (const [width, height] of [
      [1440, 900],
      [390, 844],
    ]) {
      await second.setViewportSize({ width, height });
      expect(
        await second.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width + 1);
      await second.screenshot({
        path: evidencePath(`draft-conflict-${width}.png`),
        fullPage: true,
      });
    }
    await panel.getByRole("radio", { name: "保留我的修改" }).check();
    await panel.getByRole("button", { name: "采用选择并继续保存" }).click();
    await expect(saved(second)).toBeVisible();
    await expect(panel).toHaveCount(0);
    const resolved = await (await second.request.get(apiPath)).json();
    expect(resolved.revision).toBe(3);
    expect(resolved.draft.title).toBe("窗口二需要保留的标题");
    await second.getByRole("button", { name: "打开导航", exact: true }).click();
    await second.getByRole("link", { name: "研究工作台", exact: true }).click();
    await second.goBack();
    await expect(second.getByLabel("任务名称", { exact: true })).toHaveValue(
      "窗口二需要保留的标题",
    );
    let dropped = false;
    await second.route("**" + apiPath, async (route) => {
      if (route.request().method() === "PUT" && !dropped) {
        dropped = true;
        const response = await route.fetch();
        expect(response.status()).toBe(200);
        await route.abort("failed");
      } else await route.continue();
    });
    await second
      .getByLabel("任务名称", { exact: true })
      .fill("服务器已保存但回执丢失");
    await expect(
      second.getByRole("status").filter({ hasText: "保存失败，编辑仍保留" }),
    ).toBeVisible();
    const committed = await (await second.request.get(apiPath)).json();
    expect(committed.revision).toBe(4);
    await second.getByRole("button", { name: "重试保存", exact: true }).click();
    await expect(saved(second)).toBeVisible();
    const recovered = await (await second.request.get(apiPath)).json();
    expect(recovered.revision).toBe(committed.revision);
    expect(recovered.draft.title).toBe("服务器已保存但回执丢失");
    await second.reload();
    await expect(second.getByLabel("任务名称", { exact: true })).toHaveValue(
      recovered.draft.title,
    );
    await writeFile(
      evidencePath("draft-conflict-recovery.json"),
      JSON.stringify(
        {
          task_id: taskID,
          conflict_fields: ["title"],
          conflict_selections: 1,
          conflict_confirmations: 1,
          retyped_recovery_fields: 0,
          dropped_successful_response: dropped,
          retry_clicks: 1,
          server_revision_before_retry: committed.revision,
          server_revision_after_retry: recovered.revision,
          navigation_and_reload_verified: true,
          scope:
            "Actual isolated API and two browser sessions; scientific group merging covered separately by unit tests",
        },
        null,
        2,
      ),
    );
  } finally {
    await context.close();
  }
});
