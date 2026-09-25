import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("admin and viewer paths, project context and last-keystroke preservation", async ({
  page,
  browser,
}) => {
  test.setTimeout(120000);
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("link", { name: "系统管理", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "系统管理", exact: true }),
  ).toBeVisible();
  const projectName = "浏览器隔离项目 " + Date.now(),
    email = "viewer." + Date.now() + "@example.test",
    password = "isolated-test-password-34928";
  await page.getByLabel("新项目名称", { exact: true }).fill(projectName);
  const creation = page.waitForResponse(
    (r) => r.url().endsWith("/api/projects") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "建立项目", exact: true }).click();
  const response = await creation;
  expect(response.status()).toBe(201);
  const project = await response.json();
  await expect(
    page.getByRole("combobox", { name: "当前项目", exact: true }),
  ).toHaveValue(project.id);
  await page.getByLabel("新账号邮箱", { exact: true }).fill(email);
  await page.getByLabel("初始密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "建立账号", exact: true }).click();
  await expect(page.getByLabel("新账号邮箱", { exact: true })).toHaveValue("");
  await page.getByLabel("搜索可添加账号", { exact: true }).fill(email);
  await page
    .getByRole("combobox", { name: "成员账号", exact: true })
    .selectOption({ label: email });
  await page
    .getByRole("combobox", { name: "项目角色", exact: true })
    .selectOption("viewer");
  await page.getByRole("button", { name: "保存成员角色", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "修改 " + email, exact: true }),
  ).toBeVisible();
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [390, 844],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width!);
    await page.screenshot({
      path: evidencePath(`admin-${width}.png`),
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("link", { name: "任务目录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  await page.getByLabel("任务名称", { exact: true }).fill("跨项目草稿");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/tasks\/[a-z0-9]+$/);
  const taskURL = page.url();
  await page
    .getByLabel("任务名称", { exact: true })
    .fill("切换项目也保留最后一个字");
  await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .selectOption(access.project_id);
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "当前项目", exact: true }),
  ).toHaveValue(access.project_id);
  await page.goto(taskURL);
  await expect(page.getByLabel("任务名称", { exact: true })).toHaveValue(
    "切换项目也保留最后一个字",
  );
  await expect(
    page.getByRole("combobox", { name: "当前项目", exact: true }),
  ).toHaveValue(project.id);
  const context = await browser.newContext();
  const viewer = await context.newPage();
  await viewer.goto("/");
  await viewer.getByLabel("邮箱", { exact: true }).fill(email);
  await viewer.getByLabel("密码", { exact: true }).fill(password);
  await viewer.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    viewer.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  await expect(
    viewer.getByRole("link", { name: "系统管理", exact: true }),
  ).toHaveCount(0);
  await viewer.goto(taskURL);
  await expect(viewer.getByLabel("任务名称", { exact: true })).toBeDisabled();
  await expect(
    viewer.getByRole("button", { name: "预检并执行", exact: true }),
  ).toBeDisabled();
  expect((await viewer.request.get("/api/accounts")).status()).toBe(403);
  await viewer.goto("/admin?project=" + project.id);
  await expect(viewer.getByRole("alert")).toContainText(
    "没有系统或此项目的管理权限",
  );
  await context.close();
  await writeFile(
    evidencePath("administration.json"),
    JSON.stringify(
      {
        status: "PASS",
        project_id: project.id,
        project_name: projectName,
        task_url: taskURL,
        admin_account_management: "PASS",
        viewer_unauthorized_admin: "DENIED",
        viewer_task_edit: "DISABLED",
        project_switch_and_direct_task: "PASS",
        last_keystroke_preserved: true,
        credentials_recorded: false,
      },
      null,
      2,
    ),
  );
});
