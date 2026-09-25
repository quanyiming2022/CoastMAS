import { test, expect } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import { evidenceDirectory, evidencePath } from "./evidence";

test("native planning units prepare in the same task and display their actual spatial artifact", async ({
  page,
}) => {
  test.setTimeout(120000);
  if (!process.env.COASTMAS_NEXT_TEST_URL?.endsWith(":58013"))
    throw new Error("isolated development only");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE!, "utf8"),
  );
  await mkdir(evidenceDirectory, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/research");
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
      data: { name: "规划单元工程验收 " + Date.now() },
    })
  ).json();
  const task = await (
    await page.request.post("/api/tasks", {
      headers,
      data: {
        project_id: project.id,
        title: "规划单元完整链工程夹具",
        task_type: "planning",
      },
    })
  ).json();
  const collection = {
    type: "FeatureCollection",
    features: [
      ["a", 113, 2],
      ["b", 113.001, 5],
    ].map(([id, x, cost]) => ({
      type: "Feature",
      id,
      properties: { cost },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [Number(x), 22],
            [Number(x) + 0.001, 22],
            [Number(x) + 0.001, 22.001],
            [Number(x), 22.001],
            [Number(x), 22],
          ],
        ],
      },
    })),
  };
  await page.goto(`/tasks/${task.id}?project=${project.id}`);
  await page.getByRole("button", { name: /^数据 ·/ }).click();
  await page
    .getByRole("complementary", { name: "研究共用右侧面板" })
    .getByRole("button", { name: "添加资料", exact: true })
    .click();
  const importer = page.getByRole("dialog", { name: "添加研究输入" });
  await importer
    .getByRole("button", { name: "导入新资料", exact: true })
    .click();
  await importer.getByLabel("选择并导入资料", { exact: true }).setInputFiles({
    name: "工程夹具分区.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(JSON.stringify(collection)),
  });
  await expect(
    page.getByRole("tab", { name: "输入 1", exact: true }),
  ).toBeVisible();
  await importer.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: /^准备与对齐 ·/ }).click();
  const panel = page.getByRole("region", { name: "规划单元准备", exact: true });
  await expect(panel).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "生成规划单元", exact: true }),
  ).toBeEnabled();
  const before = await (await page.request.get(`/api/tasks/${task.id}`)).json();
  expect(before.draft.method_id).toBeNull();
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().includes("/processing-nodes/") && r.url().endsWith("/execute"),
  );
  await panel
    .getByRole("button", { name: "生成规划单元", exact: true })
    .click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect
    .poll(async () =>
      (await page.request.get(`/api/jobs/${job.id}/result`)).status(),
    )
    .toBe(200);
  const result = await (
    await page.request.get(`/api/jobs/${job.id}/result`)
  ).json();
  expect(result.data.statistics.unit_count).toBe(2);
  expect(result.data.scope).toBe("full_layer");
  expect(result.data.units[0].area_m2).toBeGreaterThan(10000);
  await expect(
    page.getByRole("region", { name: "本次矢量成果地图", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("status", { name: "矢量图层就绪", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "关闭右侧面板", exact: true }).click();
  await page.getByRole("button", { name: "样式", exact: true }).click();
  const opacity = page.getByLabel("不透明度", { exact: true });
  await opacity.press("Home");
  for (let i = 0; i < 12; i++) await opacity.press("ArrowRight");
  await page.getByRole("button", { name: "关闭右侧面板", exact: true }).click();
  const canvas = page.locator(".vector-result .maplibregl-canvas");
  await canvas.click({
    position: {
      x: (await canvas.boundingBox())!.width * 0.5 - 12,
      y: (await canvas.boundingBox())!.height * 0.5,
    },
  });
  await expect(
    page.getByRole("region", { name: "点查结果", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "点查结果", exact: true }),
  ).toContainText("area_m2");
  const native = await (
    await page.request.get(`/api/jobs/${job.id}/result`)
  ).json();
  expect(native.data.units).toEqual(result.data.units);
  await page.getByRole("button", { name: "关闭右侧面板", exact: true }).click();
  for (const size of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
  ]) {
    await page.setViewportSize(size);
    await expect(canvas).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page.mouse.move(10, 10);
    await page.screenshot({
      path: evidencePath(`planning-units-${size.width}.png`),
    });
  }
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/jobs/${job.id}/view-state`)
          ).json()
        ).state?.opacity,
    )
    .toBe(0.6);
  const view = await (
    await page.request.get(`/api/jobs/${job.id}/view-state`)
  ).json();
  await page.reload();
  await expect(
    page.getByRole("status", { name: "矢量图层就绪", exact: true }),
  ).toBeVisible();
  expect(
    (await (await page.request.get(`/api/jobs/${job.id}/view-state`)).json())
      .state.opacity,
  ).toBe(0.6);
  const file = await page.request.get(
    `/api/jobs/${job.id}/artifacts/1/download`,
  );
  expect(file.status()).toBe(200);
  const bytes = await file.body(),
    hash = createHash("sha256").update(bytes).digest("hex");
  expect(hash).toBe(
    result.data.files.find(
      (f: { name: string }) => f.name === "planning-units.geojson",
    ).sha256,
  );
  await writeFile(evidencePath("planning-units.geojson"), bytes);
  const layers = page.getByLabel("当前研究成果图层组", { exact: true });
  await layers
    .getByRole("button", { name: "图层 规划单元 更多操作", exact: true })
    .click();
  await layers.getByRole("button", { name: "移出地图", exact: true }).click();
  await expect(
    layers.getByRole("checkbox", { name: "显示 规划单元", exact: true }),
  ).toHaveCount(0);
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/jobs/${job.id}/view-state`)
          ).json()
        ).state?.vector_present,
    )
    .toBe(false);
  await page.reload();
  await expect(
    page.getByRole("status", { name: "矢量图层隐藏", exact: true }),
  ).toBeVisible();
  await page.getByText("添加可用成果图层 (1)",{exact:true}).click();
  await page.getByLabel("当前研究成果图层组",{exact:true}).getByRole("button",{name:"规划单元",exact:true}).click();
  await expect(
    page.getByRole("status", { name: "矢量图层就绪", exact: true }),
  ).toBeVisible();
  const persisted = await (
    await page.request.get(`/api/tasks/${task.id}`)
  ).json();
  expect(persisted).toEqual(before);
  expect(
    (await (await page.request.get(`/api/projects/${project.id}/tasks`)).json())
      .length,
  ).toBe(1);
  await writeFile(
    evidencePath("planning-units-flow.json"),
    JSON.stringify(
      {
        project: project.id,
        task: task.id,
        job: job.id,
        manifest: result.manifest,
        statistics: result.data.statistics,
        view,
        sha256: hash,
        actions: {
          uploads: 1,
          prepare_clicks: 1,
          technical_fields: 0,
          scientific_fields: 0,
        },
        origin_kind: "engineering_fixture",
      },
      null,
      2,
    ),
  );
});
