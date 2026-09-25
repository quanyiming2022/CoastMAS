import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";
test("real 1 input, 4 output, 2 run research: compact contents and one right process inspector retain fixed science and camera", async ({
  page,
}) => {
  test.setTimeout(180000);
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  const fixture = JSON.parse(
    await readFile(process.env.COASTMAS_LAYOUT_FIXTURE!, "utf8"),
  );
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research?project=" + fixture.project);
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
  const taskURL = `/api/tasks/${fixture.task_id}`,
    jobURL = `/api/jobs/${fixture.run_id}`,
    workspaceURL = `/api/projects/${fixture.project}/workspace-state`;
  const oldContext = await (await page.request.get(workspaceURL)).json();
  expect(
    (
      await page.request.put(workspaceURL, {
        headers,
        data: {
          expected_revision: oldContext.revision,
          state: {
            ...oldContext.state,
            active_task_id: fixture.task_id,
            viewed_job_id: fixture.run_id,
            central_view: "result",
            drawer: "closed",
            content_tab: "layers",
          },
        },
      })
    ).ok(),
  ).toBe(true);
  const descriptor = await (
    await page.request.get(jobURL + "/descriptor")
  ).json();
  const outputs = descriptor.outputs.filter(
    (o: { view_kind: string }) => o.view_kind === "raster",
  );
  expect(outputs).toHaveLength(4);
  const initialView = await (
    await page.request.get(jobURL + "/view-state")
  ).json();
  expect(
    (
      await page.request.put(jobURL + "/view-state", {
        headers,
        data: {
          expected_revision: initialView.revision,
          state: {
            asset_id: null,
            artifact_id: "0",
            band: 1,
            camera: null,
            visible: true,
            opacity: 0.6,
            layers: outputs.map((o: { id: string }) => ({
              artifact_id: o.id,
              visible: o.id === "0",
              opacity: 0.6,
            })),
          },
        },
      })
    ).ok(),
  ).toBe(true);
  await page.reload();
  const result = page.locator(".research-result"),
    manager = page.getByRole("complementary", { name: "研究内容管理器" }),
    inspector = page.getByRole("complementary", { name: "研究共用右侧面板" }),
    rail = page.getByRole("navigation", { name: "研究环节" });
  await expect(
    result.getByRole("status", { name:"图层就绪", exact: true }),
  ).toBeVisible({ timeout: 60000 });
  await expect(
    manager.getByRole("tab", { name: "输入 1", exact: true }),
  ).toBeVisible();
  await expect(
    manager.getByRole("tab", { name: "运行 2", exact: true }),
  ).toBeVisible();
  const draft = await (await page.request.get(taskURL)).json(),
    jobs = await (await page.request.get(taskURL + "/jobs")).json(),
    frozen = await (await page.request.get(jobURL + "/result")).json();
  const geometry = [];
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
  ]) {
    await page.setViewportSize({ width: width!, height: height! });
    const map = await result
        .getByRole("region", { name: "资料地图", exact: true })
        .boundingBox(),
      left = await manager.boundingBox(),
      right = await rail.boundingBox();
    expect(left!.width).toBeGreaterThanOrEqual(260);
    expect(left!.width).toBeLessThanOrEqual(280);
    expect(right!.width).toBe(72);
    expect(map!.x + map!.width).toBeLessThanOrEqual(right!.x);
    expect(map!.y).toBeLessThanOrEqual(160);
    if (width === 1440) expect(map!.height).toBeGreaterThanOrEqual(650);
    await expect(rail.getByRole("button")).toHaveCount(8);
    for (const button of await rail.getByRole("button").all()) {
      await expect(button).toBeInViewport();
      const b = await button.boundingBox();
      expect(b!.height).toBeGreaterThanOrEqual(56);
      expect(b!.height).toBeLessThanOrEqual(60);
    }
    for (const row of await manager.locator(".compact-layers>li").all())
      expect((await row.boundingBox())!.height).toBe(40);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width!);
    await page.screenshot({
      path: evidencePath(`research-panels-after-${width}.png`),
    });
    geometry.push({ width, height, map, left, right });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const canvas = result.getByRole("region", { name: "资料地图", exact: true });
  const retained = await canvas.elementHandle();
  await canvas.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(jobURL + "/view-state")).json()).state
          .camera,
    )
    .not.toBeNull();
  const camera = (await (await page.request.get(jobURL + "/view-state")).json())
    .state.camera;
  const pixelResponse = page.waitForResponse((r) =>
    r.url().endsWith(`${jobURL.slice(4)}/artifacts/0/inspect`),
  );
  const box = await canvas.locator("canvas").boundingBox();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  const pixel = await (await pixelResponse).json();
  expect(pixel.sha256).toBe(frozen.data.files[0].sha256);
  await expect(inspector.getByLabel("点查结果", { exact: true })).toBeVisible();
  for (let i = 0; i < 8; i++) {
    const step = rail.getByRole("button").nth(i);
    await step.click();
    await expect(step).toHaveAttribute("aria-current", "step");
    await expect(inspector.getByLabel("作用范围", { exact: true })).toHaveValue(
      "draft",
    );
    expect((await inspector.boundingBox())!.width).toBe(320);
    await expect(
      inspector.getByLabel("点查结果", { exact: true }),
    ).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(step).toBeFocused();
    await expect(inspector).toBeHidden();
  }
  const weights = rail.getByRole("button").nth(5);
  await weights.focus();
  await page.keyboard.press("Enter");
  await inspector.getByLabel("作用范围", { exact: true }).selectOption("run");
  await expect(
    inspector.getByText(
      `固定运行 ${fixture.run_id.slice(0, 8)} · 配置 v${descriptor.draft_revision}`,
      { exact: true },
    ),
  ).toBeVisible();
  await expect(inspector.locator(".research-step-editor")).toBeHidden();
  await page.screenshot({
    path: evidencePath("research-panels-fixed-step.png"),
  });
  await page.keyboard.press("Escape");
  const toolbar = result.getByRole("toolbar", { name: "成果工具条" });
  await toolbar.getByRole("button", { name: "详情", exact: true }).click();
  await expect(inspector.getByLabel("点查结果", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  const beforeLayers = (
    await (await page.request.get(jobURL + "/view-state")).json()
  ).state.layers;
  await manager.getByLabel("搜索当前图层").fill("没有匹配的层");
  await expect(manager.locator(".compact-layers>li")).toHaveCount(0);
  expect(
    (await (await page.request.get(jobURL + "/view-state")).json()).state
      .layers,
  ).toEqual(beforeLayers);
  await manager.getByLabel("搜索当前图层").clear();
  await manager.getByRole("button", { name: "管理", exact: true }).click();
  await manager.getByLabel("批选筛选图层").check();
  expect(
    (await (await page.request.get(jobURL + "/view-state")).json()).state
      .layers,
  ).toEqual(beforeLayers);
  expect(
    (await (await page.request.get(workspaceURL)).json()).state.active_task_id,
  ).toBe(fixture.task_id);
  await manager.getByRole("button", { name: "管理", exact: true }).click();
  const second = manager.locator(".compact-layers>li").nth(1);
  await second.locator("input[type=checkbox]").check();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(jobURL + "/view-state")).json()).state
          .layers[1].visible,
    )
    .toBe(true);
  await second
    .getByRole("button", {
      name: outputs[1].title ?? outputs[1].name,
      exact: true,
    })
    .click();
  await expect(inspector).toBeVisible();
  await page.keyboard.press("Escape");
  expect(
    (await (await page.request.get(jobURL + "/view-state")).json()).state
      .layers[0].visible,
  ).toBe(true);
  await toolbar.getByRole("button", { name: "样式", exact: true }).click();
  await inspector
    .getByRole("slider", { name: "不透明度", exact: true })
    .fill("0.65");
  await expect(page.locator(".research-save-status")).toHaveText("已保存");
  await page.keyboard.press("Escape");
  await manager.getByRole("tab", { name: "输入 1", exact: true }).click();
  await expect(
    manager.getByText("输入资料 1项", { exact: true }),
  ).toBeVisible();
  await manager.getByRole("tab", { name: "运行 2", exact: true }).click();
  await expect(manager.locator(".compact-runs>li")).toHaveCount(2);
  await expect(manager.locator(".compact-runs")).not.toContainText("succeeded");
  await manager.getByRole("tab", { name: "图层", exact: true }).click();
  expect(await retained!.evaluate((el) => el.isConnected)).toBe(true);
  expect(
    (await (await page.request.get(jobURL + "/view-state")).json()).state
      .camera,
  ).toEqual(camera);
  // Historical switch uses each run's own descriptor and does not edit the active draft.
  await manager.getByRole("tab", { name: "运行 2", exact: true }).click();
  const other = jobs.items.find((j: { id: string }) => j.id !== fixture.run_id);
  await manager
    .getByRole("button", { name: new RegExp("^#" + other.id.slice(0, 8)) })
    .click();
  await expect(toolbar.locator(".run-identity")).toContainText(
    other.id.slice(0, 8),
  );
  await manager
    .getByRole("button", {
      name: new RegExp("^#" + fixture.run_id.slice(0, 8)),
    })
    .click();
  await expect(toolbar.locator(".run-identity")).toContainText(
    fixture.run_id.slice(0, 8),
  );
  await manager.getByRole("tab", { name: "图层", exact: true }).click();
  await toolbar.getByLabel("成果图层", { exact: true }).selectOption("3");
  await toolbar.getByRole("button", { name: "导出", exact: true }).click();
  const href = await result
    .getByRole("link", { name: "下载实际成果", exact: true })
    .getAttribute("href");
  expect(href).toBe(jobURL + "/artifacts/3/download");
  const download = await page.request.get(href!);
  expect(download.ok()).toBe(true);
  expect(
    createHash("sha256")
      .update(await download.body())
      .digest("hex"),
  ).toBe(frozen.data.files[3].sha256);
  await page.keyboard.press("Escape");
  await manager.getByRole("tab", { name: "输入 1", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await page.request.get(workspaceURL)).json()).state.content_tab,
    )
    .toBe("inputs");
  await page.reload();
  await expect(manager.getByRole("tab", { name: "输入 1" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(toolbar.locator(".run-identity")).toContainText(
    fixture.run_id.slice(0, 8),
  );
  expect(await (await page.request.get(taskURL)).json()).toEqual(draft);
  expect(await (await page.request.get(taskURL + "/jobs")).json()).toEqual(
    jobs,
  );
  expect(await (await page.request.get(jobURL + "/result")).json()).toEqual(
    frozen,
  );
  expect(errors).toEqual([]);
  await writeFile(
    evidencePath("research-panels.json"),
    JSON.stringify(
      {
        fixture,
        geometry,
        camera,
        pixel,
        inputs: 1,
        outputs: 4,
        runs: 2,
        draft_unchanged: true,
        frozen_result_unchanged: true,
        no_extra_jobs: true,
        manual_tabs_restored: true,
        shared_panel_focus_and_8_steps: true,
        download_sha256: frozen.data.files[3].sha256,
      },
      null,
      2,
    ),
  );
});
