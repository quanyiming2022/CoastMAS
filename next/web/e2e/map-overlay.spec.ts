import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";
test("compact optional legends and truthful toolbar/save states follow actual layer and frozen run", async ({
  page,
}) => {
  test.setTimeout(180000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  const f = JSON.parse(
    await readFile(process.env.COASTMAS_LAYOUT_FIXTURE!, "utf8"),
  );
  const stress = JSON.parse(
    await readFile(process.env.COASTMAS_PANEL_STRESS_FIXTURE!, "utf8"),
  );
  await page.setViewportSize({ width: 1440, height: 900 });
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
  const result = page.locator(".research-result"),
    toolbar = result.getByRole("toolbar", { name: "成果工具条" }),
    inspector = page.getByRole("complementary", { name: "研究共用右侧面板" }),
    manager = page.getByRole("complementary", { name: "研究内容管理器" });
  async function activate(project: string, task: string, run: string) {
    const root = `/api/projects/${project}/workspace-state`,
      old = await (await page.request.get(root)).json();
    expect(
      (
        await page.request.put(root, {
          headers,
          data: {
            expected_revision: old.revision,
            state: {
              ...old.state,
              active_task_id: task,
              viewed_job_id: run,
              inspected_asset_id: null,
              central_view: "result",
              content_tab: "layers",
              drawer: "closed",
            },
          },
        })
      ).ok(),
    ).toBe(true);
    const url = `/api/jobs/${run}/view-state`,
      view = await (await page.request.get(url)).json();
    expect(
      (
        await page.request.put(url, {
          headers,
          data: {
            expected_revision: view.revision,
            state: {
              asset_id: null,
              artifact_id: "0",
              band: 1,
              visible: true,
              opacity: 0.6,
              camera: null,
              legend_visible: false,
            },
          },
        })
      ).ok(),
    ).toBe(true);
    await page.goto("/research?project=" + project);
    await page.reload();
    await expect(
      toolbar.getByRole("status", { name: "图层就绪", exact: true }),
    ).toBeVisible({ timeout: 45000 });
  }
  await activate(f.project, f.task_id, f.run_id);
  const taskBefore = await (
      await page.request.get(`/api/tasks/${f.task_id}`)
    ).json(),
    jobsBefore = await (
      await page.request.get(`/api/tasks/${f.task_id}/jobs`)
    ).json(),
    resultBefore = await (
      await page.request.get(`/api/jobs/${f.run_id}/result`)
    ).json();
  await mkdir(evidenceDirectory, { recursive: true });
  const geometry = [];
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    await expect(
      result.getByRole("region", { name: "地图图例", exact: true }),
    ).toHaveCount(0);
    await expect(result.locator(".result-map-notices")).toHaveCount(0);
    await expect(
      toolbar.getByText("工程结果 · 待验证", { exact: true }),
    ).toBeVisible();
    await expect(result.locator(".maplibregl-ctrl-attrib")).toBeVisible();
    await expect(result.locator(".maplibregl-ctrl-scale")).toBeVisible();
    await page.screenshot({
      path: evidencePath(`map-overlay-after-${width}.png`),
    });
    geometry.push({
      width,
      height,
      map: await result
        .getByRole("region", { name: "资料地图", exact: true })
        .boundingBox(),
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await toolbar.getByRole("button", { name: "样式", exact: true }).click();
  await expect(
    inspector.getByRole("region", { name: "完整图例", exact: true }),
  ).toBeVisible();
  const toggle = inspector.getByRole("checkbox", {
    name: "显示地图图例",
    exact: true,
  });
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  await page.keyboard.press("Escape");
  const legend = result.getByRole("region", { name: "地图图例", exact: true });
  await expect(legend).toBeVisible();
  const box = await legend.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(160);
  expect(box!.width).toBeLessThanOrEqual(200);
  expect(box!.height).toBeGreaterThanOrEqual(48);
  expect(box!.height).toBeLessThanOrEqual(64);
  const scale = await result.locator(".maplibregl-ctrl-scale").boundingBox();
  expect(box!.y + box!.height).toBeLessThan(scale!.y);
  await page.screenshot({
    path: evidencePath("map-overlay-compact-continuous.png"),
  });
  await page.reload();
  await expect(legend).toBeVisible();
  await manager
    .locator(".compact-layers>li")
    .first()
    .getByRole("checkbox")
    .uncheck();
  await expect(legend).toHaveCount(0);
  await manager
    .locator(".compact-layers>li")
    .first()
    .getByRole("checkbox")
    .check();
  await expect(legend).toBeVisible();
  // Different active, hidden layer: no stale composite legend.
  await toolbar.getByLabel("成果图层", { exact: true }).selectOption("3");
  await expect(legend).toHaveCount(0);
  const quality = manager.locator(".compact-layers>li").nth(3);
  await quality.getByRole("checkbox").check();
  await expect(legend).toContainText("共同有效范围");
  await expect(legend.getByRole("listitem")).toHaveCount(2);
  await page.screenshot({ path: evidencePath("map-overlay-quality.png") });
  expect(
    await (await page.request.get(`/api/tasks/${f.task_id}`)).json(),
  ).toEqual(taskBefore);
  expect(
    await (await page.request.get(`/api/tasks/${f.task_id}/jobs`)).json(),
  ).toEqual(jobsBefore);
  expect(
    await (await page.request.get(`/api/jobs/${f.run_id}/result`)).json(),
  ).toEqual(resultBefore);
  await activate(stress.project, stress.task, stress.run);
  await toolbar.getByRole("button", { name: "样式", exact: true }).click();
  await inspector
    .getByRole("checkbox", { name: "显示地图图例", exact: true })
    .check();
  await page.keyboard.press("Escape");
  await expect(legend).toContainText("预览样本值0.375");
  await expect(legend.locator(".legend-single-swatch")).toHaveCount(1);
  await expect(legend.locator(".continuous-legend")).toHaveCount(0);
  await expect(manager.locator(".compact-layers>li")).toHaveCount(30);
  await page.screenshot({ path: evidencePath("map-overlay-single-value.png") });
  for (const index of ["1", "27", "29", "0"]) {
    await toolbar.getByLabel("成果图层", { exact: true }).selectOption(index);
    const row = manager.locator(".compact-layers>li").nth(Number(index));
    await row.getByRole("checkbox").check();
    await expect(legend).toHaveCount(1);
    const title = await row.locator(".layer-name").textContent();
    await expect(legend.locator("strong")).toHaveText(title!);
  }
  // Real uploaded Float64 values and native color table, no invented bounds.
  for (const file of ["precision", "categories"]) {
    const content = await readFile(
      `${process.env.COASTMAS_LEGEND_FIXTURES}/${file}.tif`,
    );
    const response = await page.request.post(
      `/api/projects/${stress.project}/assets`,
      {
        headers,
        multipart: {
          file: {
            name: `${file}.tif`,
            mimeType: "image/tiff",
            buffer: content,
          },
        },
      },
    );
    expect(response.ok()).toBe(true);
    const asset = (await response.json()).asset;
    const root = `/api/projects/${stress.project}/workspace-state`,
      workspace = await (await page.request.get(root)).json();
    expect(
      (
        await page.request.put(root, {
          headers,
          data: {
            expected_revision: workspace.revision,
            state: {
              ...workspace.state,
              inspected_asset_id: asset.id,
              central_view: "map",
            },
          },
        })
      ).ok(),
    ).toBe(true);
    const viewURL = `/api/projects/${stress.project}/view-state`,
      view = await (await page.request.get(viewURL)).json();
    expect(
      (
        await page.request.put(viewURL, {
          headers,
          data: {
            expected_revision: view.revision,
            state: {
              asset_id: asset.id,
              band: 1,
              camera: null,
              visible: true,
              opacity: 1,
              legend_visible: true,
            },
          },
        })
      ).ok(),
    ).toBe(true);
    await page.reload();
    const raw = page
      .locator(".research-map")
      .getByRole("region", { name: "地图图例", exact: true });
    await expect(raw).toBeVisible();
    if (file === "precision") {
      await expect(raw).toContainText("0.37500001 — 0.37500002");
      await expect(raw.locator(".legend-single-swatch")).toHaveCount(0);
    } else {
      const info = await (
        await page.request.get(`/api/assets/${asset.id}/view?band=1`)
      ).json();
      expect(await raw.getByRole("listitem").count()).toBe(
        Object.keys(info.palette).length,
      );
      expect(
        await raw
          .locator("ul")
          .evaluate((e) => e.scrollHeight > e.clientHeight),
      ).toBe(true);
    }
    await page.screenshot({ path: evidencePath(`map-overlay-${file}.png`) });
  }
  await activate(f.project, f.task_id, f.run_id);
  const tilePattern = `**/jobs/${f.run_id}/artifacts/0/tiles/**`;
  let release!: () => void;
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  let received!: () => void;
  const requested = new Promise<void>((resolve) => {
    received = resolve;
  });
  await page.route(tilePattern, async (route) => {
    received();
    await released;
    await route.continue();
  });
  await page.reload();
  await requested;
  await expect(
    toolbar.getByRole("status", { name: "正在加载图层", exact: true }),
  ).toBeVisible();
  await expect(
    toolbar.getByRole("status", { name: "图层就绪", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({ path: evidencePath("map-overlay-slow-loading.png") });
  release();
  await expect(
    toolbar.getByRole("status", { name: "图层就绪", exact: true }),
  ).toBeVisible({ timeout: 45000 });
  await page.unroute(tilePattern);
  await page.route(tilePattern, (route) =>
    route.fulfill({ status: 503, body: "isolated display failure" }),
  );
  await page.reload();
  await expect(
    toolbar.getByRole("button", { name: "重试显示", exact: true }),
  ).toBeVisible();
  await expect(
    toolbar.getByRole("status", { name: "图层就绪", exact: true }),
  ).toHaveCount(0);
  await page.screenshot({
    path: evidencePath("map-overlay-display-failure.png"),
  });
  await page.unroute(tilePattern);
  await toolbar.getByRole("button", { name: "重试显示", exact: true }).click();
  await expect(
    toolbar.getByRole("status", { name: "图层就绪", exact: true }),
  ).toBeVisible({ timeout: 45000 });
  const viewPattern = `**/jobs/${f.run_id}/view-state`;
  await page.route(viewPattern, (route) =>
    route.request().method() === "PUT"
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ message: "隔离验收：视图存储暂不可用" }),
        })
      : route.continue(),
  );
  await toolbar.getByRole("button", { name: "样式", exact: true }).click();
  await inspector
    .getByRole("checkbox", { name: "显示地图图例", exact: true })
    .check();
  await expect(page.locator(".research-save-status")).toHaveText("保存失败");
  await expect(result.getByRole("alert")).toContainText("视图存储暂不可用");
  await page.screenshot({ path: evidencePath("map-overlay-save-failure.png") });
  await page.unroute(viewPattern);
  await page.reload();
  await expect(legend).toHaveCount(0);
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  const viewURL = `/api/jobs/${f.run_id}/view-state`,
    other = await (await page.request.get(viewURL)).json();
  expect(
    (
      await page.request.put(viewURL, {
        headers,
        data: {
          expected_revision: other.revision,
          state: { ...other.state, opacity: 0.55 },
        },
      })
    ).ok(),
  ).toBe(true);
  await toolbar.getByRole("button", { name: "样式", exact: true }).click();
  await inspector
    .getByRole("checkbox", { name: "显示地图图例", exact: true })
    .check();
  await expect(page.locator(".research-save-status")).toHaveText("保存冲突");
  await page.reload();
  expect(
    await (await page.request.get(`/api/tasks/${f.task_id}`)).json(),
  ).toEqual(taskBefore);
  expect(
    await (await page.request.get(`/api/jobs/${f.run_id}/result`)).json(),
  ).toEqual(resultBefore);
  await writeFile(
    evidencePath("map-overlay.json"),
    JSON.stringify(
      {
        fixture: f,
        geometry,
        compact: box,
        single_sample: 0.375,
        precision_values: [0.37500001, 0.37500002],
        real_palette_all_entries: true,
        thirty_layer_active_only: true,
        slow_load_request_held: true,
        display_failure_503_injected: true,
        display_retry_passed: true,
        save_failure_503_injected: true,
        save_conflict_real409: true,
        default_off: true,
        view_preference_persisted: true,
        science_and_run_unchanged: true,
      },
      null,
      2,
    ),
  );
});
