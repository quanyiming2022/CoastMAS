import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";

test("long names stay in one header; account keyboard and genuine draft save errors remain explicit", async ({
  page,
  request,
}) => {
  test.setTimeout(90000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  const auth = await request.post("/api/session", {
    data: { email: access.email, password: access.password },
  });
  expect(auth.ok()).toBe(true);
  const headers = { "X-CSRF-Token": (await auth.json()).csrf };
  const stamp = Date.now();
  const projectName =
    "珠江三角洲海岸带生态环境多源资料与空间综合研究项目".repeat(3) + stamp;
  const projectResponse = await request.post("/api/projects", {
    headers,
    data: { name: projectName },
  });
  expect(projectResponse.status()).toBe(201);
  const project = (await projectResponse.json()).id;
  const email =
    "coastmas.long.research.account." +
    stamp +
    "@long.institution.example.test";
  const password = randomUUID() + "!a7";
  const accountResponse = await request.post("/api/accounts", {
    headers,
    data: { email, password, system_admin: false },
  });
  expect(accountResponse.status()).toBe(201);
  const account = (await accountResponse.json()).id;
  expect(
    (
      await request.put(`/api/projects/${project}/members/${account}`, {
        headers,
        data: { role: "analyst" },
      })
    ).ok(),
  ).toBe(true);
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/research?project=" + project);
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("button", { name: "新建研究", exact: true }).click();
  const title =
    "珠江三角洲海岸带多源指标综合评价与历史成果解释—保留完整真实名称".repeat(3);
  const creation = page.getByRole("dialog", { name: "新建研究任务" });
  await creation.getByLabel("任务名称（可选）").fill(title);
  await creation.getByRole("button", { name: "创建并继续" }).click();
  await expect(page).toHaveURL(/\/tasks\//);
  const taskId = new URL(page.url()).pathname.split("/").at(-1)!;
  const draft = await (await page.request.get("/api/tasks/" + taskId)).json();
  const header = page.locator(".workspace-topbar");
  const titleButton = header.getByRole("button", {
    name: "查看或编辑研究名称",
  });
  await expect(titleButton).toHaveText(title);
  await expect(header.locator(".research-save-status")).toHaveText("已保存");
  await mkdir(evidenceDirectory, { recursive: true });
  const measurements = [];
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    const bar = await header.boundingBox();
    const execute = await header
      .getByRole("button", { name: "预检并执行", exact: true })
      .boundingBox();
    expect(bar!.height).toBe(48);
    expect(execute!.y + execute!.height).toBeLessThanOrEqual(
      bar!.y + bar!.height,
    );
    expect(execute!.x + execute!.width).toBeLessThan(width!);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width!);
    expect(
      await titleButton.evaluate((e) => e.scrollWidth > e.clientWidth),
    ).toBe(true);
    await expect(
      page.getByRole("combobox", { name: "当前项目", exact: true }),
    ).toHaveAttribute("title", projectName);
    await page.screenshot({
      path: evidencePath(`top-header-long-${width}.png`),
    });
    measurements.push({ width, height, header: bar, execute });
  }
  const menu = header.getByRole("button", { name: "账号菜单" });
  await menu.focus();
  await page.keyboard.press("Enter");
  const accountMenu = page.getByRole("dialog", { name: "账号详情" });
  await expect(accountMenu).toContainText(email);
  await page.keyboard.press("Tab");
  await expect(accountMenu.getByText(email, { exact: true })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(
    accountMenu.getByRole("button", { name: "退出登录" }),
  ).toBeFocused();
  await page.screenshot({ path: evidencePath("top-header-long-account.png") });
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await titleButton.focus();
  await page.keyboard.press("Enter");
  const nameInput = page.getByLabel("完整研究名称", { exact: true });
  await expect(nameInput).toHaveValue(title);
  const renamed = title + "（编辑验证）";
  await nameInput.fill(renamed);
  const failureRoute = `/api/tasks/${taskId}`;
  await page.route("**" + failureRoute, async (route) => {
    if (route.request().method() === "PUT")
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ message: "隔离网络失败验证" }),
      });
    else await route.continue();
  });
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(header.locator(".research-save-status")).toHaveText("保存失败");
  expect(await (await request.get("/api/tasks/" + taskId)).json()).toEqual(
    draft,
  );
  await page.unroute("**" + failureRoute);
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(
    page.getByRole("dialog", { name: "研究名称", exact: true }),
  ).not.toBeVisible();
  await expect(header.locator(".research-save-status")).toHaveText("已保存");
  const saved = await (await page.request.get("/api/tasks/" + taskId)).json();
  expect(saved.draft).toEqual({ ...draft.draft, title: renamed });
  const remote = await request.put("/api/tasks/" + taskId, {
    headers,
    data: {
      expected_revision: saved.revision,
      draft: { ...saved.draft, title: "远端不同名称" },
    },
  });
  expect(remote.ok()).toBe(true);
  await titleButton.click();
  await nameInput.fill("本地不同名称");
  await page.getByRole("button", { name: "保存名称" }).click();
  await expect(header.locator(".research-save-status")).toHaveText("保存冲突");
  expect(
    (await (await request.get("/api/tasks/" + taskId)).json()).draft.title,
  ).toBe("远端不同名称");
  expect(
    (await (await page.request.get(`/api/tasks/${taskId}/jobs`)).json()).total,
  ).toBe(0);
  await writeFile(
    evidencePath("top-header-behavior.json"),
    JSON.stringify(
      {
        project,
        taskId,
        measurements,
        long_names_unchanged_by_truncation: true,
        keyboard_account_and_title: true,
        save_failure_and_conflict_visible: true,
        renamed_via_existing_draft_contract: true,
        no_calculation_triggered: true,
      },
      null,
      2,
    ),
  );
});
