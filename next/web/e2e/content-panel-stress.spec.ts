import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";
test("real engineering stress: 30 layers, long multi-type inputs, paged runs, actual failure and revoked role", async ({
  page,
  browser,
}) => {
  test.setTimeout(150000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  const f = JSON.parse(
    await readFile(process.env.COASTMAS_PANEL_STRESS_FIXTURE!, "utf8"),
  );
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.goto("/research?project=" + f.project);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  const headers = {
    "X-CSRF-Token": (await (await page.request.get("/api/session")).json())
      .csrf,
  };
  const stateURL = `/api/projects/${f.project}/workspace-state`;
  async function activate(task: string, run: string | null, tab = "layers") {
    const old = await (await page.request.get(stateURL)).json();
    expect(
      (
        await page.request.put(stateURL, {
          headers,
          data: {
            expected_revision: old.revision,
            state: {
              ...old.state,
              active_task_id: task,
              inspected_asset_id: null,
              viewed_job_id: run,
              central_view: run ? "result" : "map",
              content_tab: tab,
              drawer: "closed",
            },
          },
        })
      ).ok(),
    ).toBe(true);
    await page.reload();
  }
  const viewURL = `/api/jobs/${f.run}/view-state`;
  const original = await (await page.request.get(viewURL)).json();
  expect(
    (
      await page.request.put(viewURL, {
        headers,
        data: {
          expected_revision: original.revision,
          state: {
            asset_id: null,
            artifact_id: "0",
            band: 1,
            camera: null,
            visible: true,
            opacity: 0.9,
          },
        },
      })
    ).ok(),
  ).toBe(true);
  await activate(f.task, f.run);
  const manager = page.getByRole("complementary", { name: "研究内容管理器" }),
    result = page.locator(".research-result");
  await expect(
    result.getByRole("status", { name: "图层就绪", exact: true }),
  ).toBeVisible({ timeout: 30000 });
  await expect(manager.locator(".compact-layers>li")).toHaveCount(30);
  const scroll = manager.locator(".layer-catalog .content-scroll");
  expect(await scroll.evaluate((e) => e.scrollHeight > e.clientHeight)).toBe(
    true,
  );
  const draft = await (await page.request.get(`/api/tasks/${f.task}`)).json();
  const map = await result
    .getByRole("region", { name: "资料地图", exact: true })
    .elementHandle();
  await manager.getByRole("button", { name: "管理", exact: true }).click();
  const first = manager.locator(".compact-layers>li").first();
  await first.getByRole("button", { name: /更多操作/ }).click();
  const menu = page.getByRole("dialog", { name: /综合评价结果 图层操作/ });
  await expect(menu).toBeVisible();
  const menuBox = await menu.boundingBox();
  expect(menuBox!.x).toBeGreaterThanOrEqual(0);
  expect(menuBox!.y + menuBox!.height).toBeLessThanOrEqual(768);
  await menu.getByRole("button", { name: "下移图层" }).click();
  await page.keyboard.press("Escape");
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${f.run}/view-state`)).json())
          .state.layers[1].artifact_id,
    )
    .toBe("0");
  expect(await (await page.request.get(`/api/tasks/${f.task}`)).json()).toEqual(
    draft,
  );
  await manager.getByLabel("搜索当前图层").fill("工程指标_14");
  await expect(manager.locator(".compact-layers>li")).toHaveCount(2);
  await manager.getByLabel("批选筛选图层").check();
  await manager.getByRole("button", { name: "移出地图 (2)" }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(`/api/jobs/${f.run}/view-state`)).json())
          .state.layers.length,
    )
    .toBe(28);
  expect(await (await page.request.get(`/api/tasks/${f.task}`)).json()).toEqual(
    draft,
  );
  await manager.getByLabel("搜索当前图层").clear();
  await manager.getByText("添加可用成果图层 (2)", { exact: true }).click();
  await manager
    .getByRole("button", { name: "标准化指标 · 工程指标_14", exact: true })
    .click();
  await manager
    .getByRole("button", { name: "加权指标 · 工程指标_14", exact: true })
    .click();
  await expect(manager.locator(".compact-layers>li")).toHaveCount(30);
  await manager.getByRole("button", { name: "管理", exact: true }).click();
  expect(await map!.evaluate((e) => e.isConnected)).toBe(true);
  await mkdir(evidenceDirectory, { recursive: true });
  await expect(
    result.getByRole("status", { name: "图层就绪", exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: evidencePath("content-panel-30-layers.png") });
  await manager.getByRole("tab", { name: "运行 12", exact: true }).click();
  await expect(manager.locator(".compact-runs>li")).toHaveCount(10);
  await manager.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(manager.locator(".compact-runs>li")).toHaveCount(2);
  await expect(
    manager.getByRole("button", { name: "下一页", exact: true }),
  ).toBeDisabled();
  expect(
    (await (await page.request.get(stateURL)).json()).state.viewed_job_id,
  ).toBe(f.run);
  await manager.getByLabel("查找运行编号").fill(f.run.slice(0, 8));
  await expect(manager.locator(".compact-runs>li")).toHaveCount(1);
  await page.screenshot({
    path: evidencePath("content-panel-runs-search.png"),
  });
  await activate(f.multitype_task, null, "inputs");
  await expect(
    manager.getByRole("tab", { name: "输入 2", exact: true }),
  ).toBeVisible();
  await expect(manager.locator(".compact-inputs>li")).toHaveCount(2);
  const inputDraft = await (
    await page.request.get(`/api/tasks/${f.multitype_task}`)
  ).json();
  const name = manager.getByRole("button", { name: f.asset_name, exact: true });
  await expect(name).toHaveAttribute("title", f.asset_name);
  expect(await name.evaluate((e) => e.scrollWidth > e.clientWidth)).toBe(true);
  await manager.getByLabel("输入资料类型").selectOption("csv");
  await expect(manager.locator(".compact-inputs>li")).toHaveCount(1);
  await manager
    .getByRole("button", { name: "独立表格参考.csv", exact: true })
    .click();
  expect(
    await (await page.request.get(`/api/tasks/${f.multitype_task}`)).json(),
  ).toEqual(inputDraft);
  await expect(
    page.getByRole("navigation", { name: "研究环节" }),
  ).toBeVisible();
  await manager.getByRole("button", { name: "添加", exact: true }).click();
  const add = page.getByRole("dialog", { name: "添加研究输入" });
  await expect(
    add.getByRole("button", { name: "从资料库选择", exact: true }),
  ).toBeVisible();
  await expect(
    add.getByRole("button", { name: "上传文件", exact: true }),
  ).toBeVisible();
  await expect(
    add.getByRole("button", { name: "已授权来源", exact: true }),
  ).toBeVisible();
  await add.getByRole("button", { name: "已授权来源", exact: true }).click();
  const importDialog = page.locator('dialog[open][aria-label="添加研究输入"]');
  await expect(
    importDialog.getByRole("heading", { name: "已授权来源", exact: true }),
  ).toBeVisible();
  await expect(importDialog.getByLabel("添加资料", { exact: true })).toBeHidden();
  const authorizedRoots = await (await page.request.get(`/api/projects/${f.project}/local-sources`)).json();
  if (authorizedRoots.length) {
    const sourceSelect = importDialog.getByRole("combobox", { name: "来源目录" });
    await expect(sourceSelect.locator("option")).toHaveText(authorizedRoots.map((root: {name: string}) => root.name));
    await expect(sourceSelect).toHaveValue(authorizedRoots[0].id);
    await expect(importDialog.getByRole("button", { name: "接入所选 0 个文件", exact: true })).toBeDisabled();
  } else {
    await expect(importDialog.getByText("当前项目和角色没有已授权目录，可使用文件上传。", {exact: true})).toBeVisible();
  }
  expect(await (await page.request.get(`/api/tasks/${f.multitype_task}`)).json()).toEqual(inputDraft);
  await importDialog.getByRole("button", { name: "关闭", exact: true }).click();
  await manager.getByRole("button", { name: "添加", exact: true }).click();
  await add.getByRole("button", { name: "上传文件", exact: true }).click();
  await expect(
    importDialog.getByRole("heading", { name: "上传文件", exact: true }),
  ).toBeVisible();
  await importDialog
    .getByLabel("添加资料", { exact: true })
    .setInputFiles({
      name: "面板上传检查.csv",
      mimeType: "text/csv",
      buffer: Buffer.from("id,value\n001,2\n"),
    });
  await expect(
    manager.getByRole("tab", { name: "输入 3", exact: true }),
  ).toBeVisible();
  await importDialog.getByRole("button", { name: "关闭", exact: true }).click();
  await manager.getByLabel("输入资料类型").selectOption("");
  await manager
    .getByRole("button", { name: "移除输入 面板上传检查.csv", exact: true })
    .click();
  await page.getByRole("button", { name: "确认移除输入", exact: true }).click();
  await expect(
    manager.getByRole("tab", { name: "输入 2", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: evidencePath("content-panel-long-inputs.png"),
  });
  await manager
    .getByRole("button", { name: "移除输入 独立表格参考.csv", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "核对移除输入的影响" }),
  ).toContainText("原始资产");
  await page.getByRole("button", { name: "确认移除输入", exact: true }).click();
  await expect(
    manager.getByRole("tab", { name: "输入 1", exact: true }),
  ).toBeVisible();
  expect((await page.request.get(`/api/assets/${f.csv}`)).ok()).toBe(true);
  await page.reload();
  await expect(
    manager.getByRole("tab", { name: "输入 1", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  // Return the isolated stress fixture draft for a repeatable later regression.
  const remaining = await (
    await page.request.get(`/api/tasks/${f.multitype_task}`)
  ).json();
  expect(
    (
      await page.request.post(`/api/tasks/${f.multitype_task}/sources`, {
        headers,
        data: { expected_revision: remaining.revision, assets: [f.csv] },
      })
    ).ok(),
  ).toBe(true);
  await activate(f.failed_task, f.failed_run, "runs");
  await expect(manager.locator(".compact-runs")).toContainText("计算失败");
  await expect(result).toContainText("所有必需指标无共同有效像元");
  await expect(
    result.getByRole("region", { name: "资料地图", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: evidencePath("content-panel-actual-failure.png"),
  });
  const email = `panel-viewer-${Date.now()}@example.test`,
    password = randomUUID() + "!7a";
  const account = await (
    await page.request.post("/api/accounts", {
      headers,
      data: { email, password, system_admin: false },
    })
  ).json();
  expect(
    (
      await page.request.put(
        `/api/projects/${f.project}/members/${account.id}`,
        { headers, data: { role: "viewer" } },
      )
    ).ok(),
  ).toBe(true);
  const ordinary = await browser.newContext({
    viewport: { width: 1366, height: 768 },
  });
  const viewer = await ordinary.newPage();
  await viewer.goto(`/research?project=${f.project}`);
  await viewer.getByLabel("邮箱", { exact: true }).fill(email);
  await viewer.getByLabel("密码", { exact: true }).fill(password);
  await viewer.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    viewer.getByRole("link", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  await viewer.goto("/tasks/" + f.task);
  await expect(
    viewer.getByRole("button", { name: "预检并执行", exact: true }),
  ).toBeDisabled();
  await viewer.getByRole("tab", { name: "输入 1", exact: true }).click();
  await expect(
    viewer.getByRole("button", { name: "添加", exact: true }),
  ).toBeDisabled();
  expect(
    (
      await page.request.delete(
        `/api/projects/${f.project}/members/${account.id}`,
        { headers },
      )
    ).ok(),
  ).toBe(true);
  expect(
    (await viewer.request.get(`/api/tasks/${f.task}/jobs?limit=10`)).status(),
  ).toBe(404);
  await viewer.reload();
  await expect(
    viewer.getByRole("complementary", { name: "研究内容管理器" }),
  ).toHaveCount(0);
  await ordinary.close();
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("content-panel-stress.json"),
    JSON.stringify(
      {
        fixture: f,
        layers: 30,
        pages: [10, 2],
        long_name_preserved: true,
        multi_type_inputs: 2,
        no_results: true,
        actual_failed_run: f.failed_run,
        permission_denied_after_revocation: true,
        map_not_remounted_by_layer_management: true,
        draft_not_changed_by_layer_management: true,
        removed_input_asset_retained: true,
        generated_engineering_fixture: true,
      },
      null,
      2,
    ),
  );
});
