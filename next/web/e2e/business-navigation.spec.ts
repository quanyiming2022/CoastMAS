import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("business routes and a real 205-task catalog preserve context and drafts", async ({
  page,
}) => {
  test.setTimeout(120000);
  const accessFile = process.env.COASTMAS_NEXT_ACCESS_FILE;
  if (!accessFile) throw new Error("Explicit isolated account required");
  const access = JSON.parse(await readFile(accessFile, "utf8"));
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  const actor = await (await page.request.get("/api/session")).json();
  const headers = { "X-CSRF-Token": actor.csrf };
  const created = await page.request.post("/api/projects", {
    headers,
    data: { name: "205任务目录隔离夹具 " + Date.now() },
  });
  expect(created.status()).toBe(201);
  const project = (await created.json()).id;
  for (let offset = 0; offset < 205; offset += 10) {
    await Promise.all(
      Array.from({ length: Math.min(10, 205 - offset) }, async (_, step) => {
        const index = offset + step;
        const response = await page.request.post("/api/tasks", {
          headers,
          data: {
            project_id: project,
            title: `目录夹具 ${String(index).padStart(3, "0")}`,
            purpose: index % 2 ? "assessment" : "inspect",
          },
        });
        expect(response.status()).toBe(201);
      }),
    );
  }
  await page.goto("/?project=" + project);
  const directory = page.getByRole("region", { name: "任务目录", exact: true });
  await expect(
    directory.getByText("共 205 项 · 第 1 页", { exact: true }),
  ).toBeVisible();
  expect(await directory.locator("tbody tr").count()).toBe(20);
  await directory.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(
    directory.getByText("共 205 项 · 第 2 页", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "综合评价", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "任务类型", exact: true })).toHaveValue(
    "assessment",
  );
  await page.getByLabel("查找任务", { exact: true }).fill("199");
  await page.getByLabel("查找任务", { exact: true }).press("Enter");
  await expect(
    directory.getByRole("link", { name: "目录夹具 199", exact: true }),
  ).toBeVisible();
  await expect(
    directory.getByText("共 1 项 · 第 1 页", { exact: true }),
  ).toBeVisible();
  await directory
    .getByRole("link", { name: "目录夹具 199", exact: true })
    .click();
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "目录夹具 199",
  );
  await expect(
    page.locator('nav[aria-label="主要功能"] a[aria-current="page"]:visible'),
  ).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "综合评价", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByLabel("任务名称", { exact: true }).fill("展开导航后保留草稿");
  await page.getByRole("button", { name: "展开导航", exact: true }).click();
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "展开导航后保留草稿",
  );
  await mkdir(evidenceDirectory, { recursive: true });
  await page.screenshot({
    path: evidencePath("business-nav-expanded-1440.png"),
  });
  await page.getByRole("button", { name: "收起导航", exact: true }).click();
  await page.reload();
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "展开导航后保留草稿",
  );
  await expect(
    page.getByRole("link", { name: "综合评价", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "打开导航", exact: true }).click();
  await page
    .getByRole("dialog", { name: "移动导航" })
    .getByRole("link", { name: "时间适配", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "移动导航" }),
  ).not.toBeVisible();
  await expect(page.getByRole("combobox", { name: "任务类型", exact: true })).toHaveValue(
    "temporal",
  );
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    /^时间适配/,
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(391);
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("business-navigation.json"),
    JSON.stringify(
      {
        project,
        fixture_tasks: 205,
        server_search: "PASS",
        server_pagination: "PASS",
        purpose_route: "PASS",
        draft_preservation: "PASS",
        mobile_drawer: "PASS",
        automatic_task_name: "PASS",
        page_errors: errors,
      },
      null,
      2,
    ),
  );
});
