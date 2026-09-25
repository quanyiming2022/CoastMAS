import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";
test("fixed run result workbench uses two rows then a full height map", async ({
  page,
}) => {
  test.setTimeout(120000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  const fixture = JSON.parse(
    await readFile(process.env.COASTMAS_LAYOUT_FIXTURE!, "utf8"),
  );
  const before = process.env.COASTMAS_LAYOUT_PHASE === "before";
  const compactTop = process.env.COASTMAS_TOP_LAYOUT === "1";
  const phase = before ? "before" : "after";
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research?project=" + fixture.project);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "研究工作台", exact: true }),
  ).toBeVisible();
  const auth = await (await page.request.get("/api/session")).json();
  const headers = { "X-CSRF-Token": auth.csrf };
  const workspace = await (
    await page.request.get(`/api/projects/${fixture.project}/workspace-state`)
  ).json();
  expect(
    (
      await page.request.put(
        `/api/projects/${fixture.project}/workspace-state`,
        {
          headers,
          data: {
            expected_revision: workspace.revision,
            state: {
              ...workspace.state,
              active_task_id: fixture.task_id,
              viewed_job_id: fixture.run_id,
              central_view: "result",
              drawer: "closed",
            },
          },
        },
      )
    ).ok(),
  ).toBe(true);
  const initialView = await (
    await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
  ).json();
  expect(
    (
      await page.request.put(`/api/jobs/${fixture.run_id}/view-state`, {
        headers,
        data: {
          expected_revision: initialView.revision,
          state: {
            ...initialView.state,
            asset_id: null,
            artifact_id: "0",
            band: 1,
            opacity: 0.6,
            visible: true,
            camera: fixture.camera ?? null,
          },
        },
      })
    ).ok(),
  ).toBe(true);
  await page.reload();
  const result = page.locator(".research-result");
  await expect(
    result.getByRole("status", { name:"图层就绪", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  const frozen = await (
    await page.request.get(`/api/jobs/${fixture.run_id}/result`)
  ).json();
  const draft = await (
    await page.request.get(`/api/tasks/${fixture.task_id}`)
  ).json();
  const jobs = await (
    await page.request.get(`/api/tasks/${fixture.task_id}/jobs`)
  )
    .json()
    .catch(() => null);
  await mkdir(evidenceDirectory, { recursive: true });
  const geometry = [];
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    const map = result.getByRole("region", { name: "资料地图", exact: true });
    const box = await map.boundingBox();
    const header = await page.locator(".workspace-topbar").boundingBox();
    const steps = await page
      .getByRole("navigation", { name: "研究环节" })
      .boundingBox();
    const tabs = await page.locator(".research-view-tabs").boundingBox();
    const tools = await result
      .getByRole("toolbar", { name: "成果工具条" })
      .boundingBox();
    geometry.push({ width, height, map: box, header, steps, tabs, tools });
    if (compactTop && !before) {
      expect(header!.height).toBeGreaterThanOrEqual(44);
      expect(header!.height).toBeLessThanOrEqual(48);
      expect(steps!.width).toBe(72);
      for (const button of await page
        .getByRole("navigation", { name: "研究环节" })
        .getByRole("button")
        .all())
        expect((await button.boundingBox())!.height).toBe(60);
      expect(tabs!.height).toBe(32);
      expect(tools!.height).toBe(36);
      await expect(
        page.getByRole("combobox", { name: "当前项目", exact: true }),
      ).toHaveCount(1);
      await expect(
        page.locator(".workspace-topbar .workspace-wordmark"),
      ).toHaveCount(0);
      await expect(
        page
          .locator(".workspace-topbar")
          .getByRole("button", { name: "预检并执行", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByRole("navigation", { name: "研究环节" }).getByRole("button"),
      ).toHaveCount(8);
      await expect(
        page.getByRole("link", { name: "项目管理", exact: true }),
      ).toBeInViewport();
      await expect(
        page.getByRole("link", { name: "用户管理", exact: true }),
      ).toBeInViewport();
    }
    await page.screenshot({
      path: evidencePath(`result-layout-${phase}-${width}.png`),
    });
    if (!before) {
      expect(box!.width).toBeGreaterThan(600);
      expect(box!.y).toBeLessThanOrEqual(compactTop ? 160 : 220);
      if (width === 1440) expect(box!.height).toBeGreaterThanOrEqual(650);
      expect(box!.y + box!.height).toBeLessThanOrEqual(height!);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width! + 1);
    }
  }
  if (!before) {
    await page.setViewportSize({ width: 1440, height: 900 });
    const toolbar = result.getByRole("toolbar", { name: "成果工具条" });
    await expect(toolbar).toBeVisible();
    const originalCanvas = await result
      .getByRole("region", { name: "资料地图", exact: true })
      .elementHandle();
    if (compactTop) {
      const region = result.getByRole("region", {
        name: "资料地图",
        exact: true,
      });
      const box = await region.boundingBox();
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
      await page.mouse.down();
      await page.mouse.move(
        box!.x + box!.width / 2 + 60,
        box!.y + box!.height / 2 + 20,
        { steps: 8 },
      );
      await page.mouse.up();
      await expect
        .poll(
          async () =>
            (
              await (
                await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
              ).json()
            ).state.camera,
        )
        .not.toBeNull();
      const beforeZoom = await (
        await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
      ).json();
      await region
        .getByRole("button", { name: "Zoom in", exact: true })
        .click();
      await expect
        .poll(
          async () =>
            (
              await (
                await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
              ).json()
            ).state.camera.zoom,
        )
        .toBeGreaterThan(beforeZoom.state.camera.zoom);
      await expect(page.locator(".research-save-status")).toHaveText("已保存");
    }
    const oldView = await (
      await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
    ).json();
    if (compactTop) {
      const account = page.getByRole("button", {
        name: "账号菜单",
        exact: true,
      });
      await account.focus();
      await page.keyboard.press("Enter");
      await expect(
        page.getByRole("dialog", { name: "账号详情", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("dialog", { name: "账号详情", exact: true }),
      ).toContainText(access.email);
      await page.keyboard.press("Escape");
      await expect(account).toBeFocused();
      const name = page.getByRole("button", {
        name: "查看或编辑研究名称",
        exact: true,
      });
      await name.focus();
      await page.keyboard.press("Enter");
      await expect(
        page.getByLabel("完整研究名称", { exact: true }),
      ).toHaveValue(draft.draft.title);
      await page.keyboard.press("Escape");
      await expect(name).toBeFocused();
      const step = page
        .getByRole("navigation", { name: "研究环节" })
        .getByRole("button")
        .nth(5);
      await step.click();
      await expect(step).toHaveAttribute("aria-current", "step");
      await expect(step).toHaveAccessibleName(/待核查.*当前查看/);
      await page
        .getByRole("button", { name: "当前运行成果", exact: true })
        .click();
      await expect(
        result.getByText("草稿已更新", { exact: true }),
      ).toBeVisible();
      await expect(page.locator(".research-save-status")).toHaveText("已保存");
      await page.getByRole("link", { name: "用户管理", exact: true }).click();
      await expect(
        page.getByRole("heading", { name: "用户管理", exact: true }).first(),
      ).toBeVisible();
      await page.getByRole("link", { name: "研究工作台", exact: true }).click();
      await expect(toolbar).toBeVisible();
      expect(
        await originalCanvas!.evaluate((element) => element.isConnected),
      ).toBe(true);
    }
    await toolbar.getByRole("button", { name: "样式", exact: true }).click();
    await page
      .getByRole("slider", { name: "不透明度", exact: true })
      .fill("0.65");
    await expect(page.locator(".research-save-status")).toHaveText("已保存");
    await toolbar.getByRole("button", { name: "样式", exact: true }).click();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByText(fixture.run_id, { exact: true }),
    ).toBeVisible();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    if (compactTop) {
      await page.setViewportSize({ width: 1366, height: 768 });
      await expect(
        result.getByRole("region", { name: "资料地图", exact: true }),
      ).toBeVisible();
      await page.setViewportSize({ width: 1440, height: 900 });
    }
    const current = await (
      await page.request.get(`/api/jobs/${fixture.run_id}/view-state`)
    ).json();
    expect(current.state.camera).toEqual(oldView.state?.camera ?? null);
    expect(current.state.opacity).toBe(0.65);
    const query = page.waitForResponse((r) =>
      r.url().endsWith(`/jobs/${fixture.run_id}/artifacts/0/inspect`),
    );
    const mapRegion = result.getByRole("region", {
      name: "资料地图",
      exact: true,
    });
    if (compactTop) {
      // Playwright's element-relative click starts inside the region border;
      // use the actual canvas rectangle for the geographic center measurement.
      const canvasBox = await mapRegion
        .locator("canvas.maplibregl-canvas")
        .boundingBox();
      await page.mouse.click(
        canvasBox!.x + canvasBox!.width / 2,
        canvasBox!.y + canvasBox!.height / 2,
      );
    } else await mapRegion.click({ position: { x: 300, y: 250 } });
    const inspectedResponse = await query;
    if (compactTop) {
      const location = inspectedResponse.request().postDataJSON();
      expect(location.longitude).toBeCloseTo(oldView.state.camera.longitude, 5);
      expect(location.latitude).toBeCloseTo(oldView.state.camera.latitude, 5);
    }
    const pixel = await inspectedResponse.json();
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByLabel("点查结果", { exact: true }),
    ).toBeVisible();
    expect(pixel.sha256).toBe(frozen.data.files[0].sha256);
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByLabel("点查结果", { exact: true }),
    ).toBeInViewport({ ratio: 0.5 });
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByLabel("本次原生像元贡献", { exact: true }),
    ).toBeAttached();
    await toolbar.getByRole("button", { name: "样式", exact: true }).click();
    await toolbar.getByRole("button", { name: "样式", exact: true }).click();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByLabel("点查结果", { exact: true }),
    ).toBeVisible();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    await page.getByRole("button", { name: "地图与资料", exact: true }).click();
    await page
      .getByRole("button", { name: "当前运行成果", exact: true })
      .click();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    await expect(
      page
        .getByRole("complementary", { name: "研究共用右侧面板" })
        .getByLabel("点查结果", { exact: true }),
    ).toBeVisible();
    await toolbar.getByRole("button", { name: "详情", exact: true }).click();
    expect(
      await originalCanvas!.evaluate((element) => element.isConnected),
    ).toBe(true);
    await page.getByRole("complementary", { name: "研究内容管理器" }).getByRole("tab", { name: "图层", exact: true }).click();
    await toolbar.getByLabel("成果图层", { exact: true }).selectOption("3");
    await page.getByRole("complementary", { name: "研究内容管理器" })
      .getByRole("checkbox", { name: /^显示 / }).nth(3).check();
    await expect(
      result.getByRole("status", { name:"图层就绪", exact: true }),
    ).toBeVisible();
    await toolbar.getByLabel("成果图层", { exact: true }).selectOption("0");
    await expect(
      result.getByRole("status", { name:"图层就绪", exact: true }),
    ).toBeVisible();
    await toolbar.getByRole("button", { name: "导出", exact: true }).click();
    await expect(
      result.getByRole("link", { name: "下载实际成果", exact: true }),
    ).toHaveAttribute(
      "href",
      `/api/jobs/${fixture.run_id}/artifacts/0/download`,
    );
    await expect(
      result.getByRole("link", { name: "下载完整成果包", exact: true }),
    ).toHaveAttribute("href", `/api/jobs/${fixture.run_id}/bundle`);
    await toolbar.getByRole("button", { name: "导出", exact: true }).click();
    expect(
      await (await page.request.get(`/api/tasks/${fixture.task_id}`)).json(),
    ).toEqual(draft);
    expect(
      await (
        await page.request.get(`/api/jobs/${fixture.run_id}/result`)
      ).json(),
    ).toEqual(frozen);
    expect(
      await (
        await page.request.get(`/api/tasks/${fixture.task_id}/jobs`)
      ).json(),
    ).toEqual(jobs);
    await writeFile(
      evidencePath("result-layout-interactions.json"),
      JSON.stringify(
        {
          fixture,
          pixel,
          computed_result_unchanged: true,
          draft_unchanged: true,
          style_preserved_camera: true,
          camera_before: oldView.state.camera,
          camera_after_resize_and_controls: current.state.camera,
          point_survived_style_and_tab: true,
          export_run_fixed: true,
        },
        null,
        2,
      ),
    );
  }
  await writeFile(
    evidencePath(`result-layout-${phase}.json`),
    JSON.stringify({ fixture, geometry, phase, jobs }, null, 2),
  );
});
