import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("planning objects are independently saved, published, compared and explicitly bound", async ({
  page,
  browser,
}) => {
  test.setTimeout(120000);
  if (!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(":58013"))
    throw new Error("isolated development only");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  await mkdir(evidenceDirectory, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "工作台", exact: true }),
  ).toBeVisible();
  const session = await (await page.request.get("/api/session")).json(),
    headers = { "X-CSRF-Token": session.csrf };
  const project = await (
    await page.request.post("/api/projects", {
      headers,
      data: { name: "规划版本工程验收 " + Date.now() },
    })
  ).json();
  const task = await (
    await page.request.post("/api/tasks", {
      headers,
      data: {
        project_id: project.id,
        title: "规划引用工程夹具",
        task_type: "planning",
      },
    })
  ).json();
  await page.goto(`/tasks/${task.id}?project=${project.id}`);
  await expect(page.getByRole("button", { name: /^规划目标 ·/ })).toBeVisible();
  const nav = page
    .locator(".workspace-rail")
    .getByRole("navigation", { name: "主要功能" });
  async function open(label: string) {
    const group = nav.getByRole("button", { name: "规划与优化", exact: true });
    if ((await group.getAttribute("aria-expanded")) !== "true")
      await group.click();
    await nav.getByRole("link", { name: label, exact: true }).click();
  }
  await open("规划目标");
  await expect(
    page.getByRole("region", { name: "规划目标", exact: true }),
  ).toBeVisible();
  const tools = page.locator(".planning-directory > .planning-toolbar");
  expect((await tools.boundingBox())!.height).toBeLessThanOrEqual(48);
  await page.screenshot({ path: evidencePath("planning-directory-1440.png") });
  await page.getByRole("button", { name: "新建规划目标", exact: true }).click();
  let modal = page.getByRole("dialog", { name: "新建规划目标", exact: true });
  await modal.getByLabel("名称", { exact: true }).fill("修复收益与成本");
  await modal.getByRole("button", { name: "创建草稿", exact: true }).click();
  modal = page.getByRole("dialog", {
    name: "规划目标 · 修复收益与成本",
    exact: true,
  });
  await modal.getByLabel("目标组织方式").selectOption("pareto_multiobjective");
  await modal.getByLabel("减少建设成本", { exact: true }).check();
  await modal.getByLabel("增加生态修复收益", { exact: true }).check();
  await expect(modal.getByRole("status", { name: "" }).first()).toHaveText(
    "已保存",
  );
  await expect(modal.getByLabel(/权重$/)).toHaveCount(0);
  await modal
    .getByRole("button", { name: "发布配置版本", exact: true })
    .click();
  await expect(modal).toContainText("已发布固定配置");
  const before = await (await page.request.get("/api/tasks/" + task.id)).json();
  expect(before.draft.options.planning_refs).toBeUndefined();
  await modal.getByRole("button", { name: "应用此版本", exact: true }).click();
  await expect(modal).toContainText("已将固定版本 v1 应用");
  const applied = await (
      await page.request.get("/api/tasks/" + task.id)
    ).json(),
    ref = applied.draft.options.planning_refs.objectives;
  const first = await (
    await page.request.get(
      `/api/v1/projects/${project.id}/planning/objectives/${ref.object_id}/versions/${ref.version_id}`,
    )
  ).json();
  expect(first.body.items).toHaveLength(2);
  expect(
    first.body.items.every((i: Record<string, unknown>) => !("weight" in i)),
  ).toBe(true);
  // A second authenticated browser edits the same object. The first must show 412,
  // preserving its proposal and the actual server value for an explicit decision.
  const context2 = await browser.newContext({
    storageState: await page.context().storageState(),
  });
  const second = await context2.newPage();
  await second.goto(
    `http://127.0.0.1:58013/planning/objectives?project=${project.id}`,
  );
  const url = `/api/v1/projects/${project.id}/planning/objectives/${ref.object_id}`;
  const current = await (await second.request.get(url)).json();
  const concurrent = await second.request.put(url, {
    headers: { ...headers, "If-Match": `"${current.revision}"` },
    data: { name: "服务器名称", body: current.body },
  });
  expect(concurrent.status()).toBe(200);
  await modal.getByLabel("名称", { exact: true }).fill("我的修复方案");
  await expect(
    modal.getByRole("region", { name: "版本冲突对比" }),
  ).toBeVisible();
  await expect(modal).toContainText("服务器名称");
  await expect(modal).toContainText("我的修复方案");
  await page.screenshot({ path: evidencePath("planning-conflict-1440.png") });
  await modal.getByRole("button", { name: "保留我的修改并重新保存" }).click();
  await expect(modal.getByRole("status").first()).toHaveText("已保存");
  await modal
    .getByRole("button", { name: "发布配置版本", exact: true })
    .click();
  await expect(modal).toContainText("v2 · 我的修复方案");
  expect(
    (await (await page.request.get("/api/tasks/" + task.id)).json()).draft
      .options.planning_refs.objectives,
  ).toEqual(ref);
  expect(
    await (await page.request.get(url + "/versions/" + ref.version_id)).json(),
  ).toEqual(first);
  await modal.getByRole("button", { name: "关闭", exact: true }).click();
  await context2.close();
  await open("约束库");
  await page.getByRole("button", { name: "新建约束库", exact: true }).click();
  modal = page.getByRole("dialog", { name: "新建约束库", exact: true });
  await modal.getByLabel("名称", { exact: true }).fill("工程面积上限");
  await modal.getByRole("button", { name: "创建草稿" }).click();
  modal = page.getByRole("dialog", { name: "约束库 · 工程面积上限" });
  await modal.getByLabel("添加业务约束").selectOption("development_quota");
  await modal.getByLabel("上限", { exact: true }).fill("30");
  await modal.getByLabel("适用依据").fill("明确标记的工程夹具，不是政策默认值");
  await modal.getByRole("button", { name: "发布配置版本" }).click();
  await expect(modal).toContainText("已发布固定配置");
  await modal.getByRole("button", { name: "应用此版本" }).click();
  await expect(modal).toContainText("已将固定版本 v1 应用");
  await modal.getByRole("button", { name: "关闭", exact: true }).click();
  await open("决策变量");
  await page.getByRole("button", { name: "新建决策变量", exact: true }).click();
  modal = page.getByRole("dialog", { name: "新建决策变量", exact: true });
  await modal.getByLabel("名称", { exact: true }).fill("工程修复单元");
  await modal.getByRole("button", { name: "创建草稿" }).click();
  modal = page.getByRole("dialog", { name: "决策变量 · 工程修复单元" });
  await modal
    .getByLabel("允许优化器改变什么")
    .selectOption("RestorationPlanning");
  await modal.getByRole("button", { name: "发布配置版本" }).click();
  await expect(modal).toContainText("已发布固定配置");
  await modal.getByRole("button", { name: "应用此版本" }).click();
  await expect(modal).toContainText("已将固定版本 v1 应用");
  await page.screenshot({ path: evidencePath("planning-decision-1440.png") });
  await modal.getByRole("button", { name: "关闭", exact: true }).click();
  await page.goto(`/tasks/${task.id}?project=${project.id}`);
  await page.getByRole("button", { name: /^规划目标 ·/ }).click();
  await expect(
    page.getByRole("region", { name: "规划目标绑定" }),
  ).toContainText("已引用固定版本 v1");
  await page.getByRole("button", { name: /^约束与决策变量 ·/ }).click();
  await expect(
    page.getByRole("region", { name: "约束绑定", exact: true }),
  ).toContainText("已引用固定版本 v1");
  await expect(
    page.getByRole("region", { name: "决策变量绑定" }),
  ).toContainText("已引用固定版本 v1");
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [1920, 1080],
    [2560, 1440],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    await page.locator(".research-inspector-heading h2").click();
    await page.mouse.move(10, 10);
    await page.screenshot({
      path: evidencePath(`planning-bindings-${width}.png`),
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  const saved = await (await page.request.get("/api/tasks/" + task.id)).json();
  expect(Object.keys(saved.draft.options.planning_refs).sort()).toEqual([
    "constraints",
    "decisions",
    "objectives",
  ]);
  expect(
    await (await page.request.get(`/api/tasks/${task.id}/jobs`)).json(),
  ).toEqual({ items: [], total: 0, limit: 25, offset: 0 });
  await writeFile(
    evidencePath("planning-objects.json"),
    JSON.stringify(
      {
        project: project.id,
        task: task.id,
        refs: saved.draft.options.planning_refs,
        first_version: first,
        concurrency_status: concurrent.status(),
        conflict: 412,
        task_not_automatically_upgraded: true,
        engineering_only: true,
        solver_and_reevaluation: "NOT_RUN",
      },
      null,
      2,
    ),
  );
});
