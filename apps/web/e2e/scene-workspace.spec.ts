import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test.beforeEach(async ({ page }) => {
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(
        await readFile(
          new URL(
            "../../../artifacts/runtime/demo-access.json",
            import.meta.url,
          ),
          "utf8",
        ),
      ),
    );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
});

test("map drawing, AOI upload, pinned entities/data, coverage and immutable scene revisions", async ({
  page,
}) => {
  test.setTimeout(90000);
  const aoi = JSON.parse(
    await readFile(
      new URL("../../../sample-data/coastal_aoi.geojson", import.meta.url),
      "utf8",
    ),
  ).features[0];
  const project = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "coastmas_csrf",
  )!.value;
  const name = `浏览器场景 ${Date.now()}`;
  const entityId = `scene-entity-${Date.now()}`;
  const entity = await page.request.post("/api/v1/entities", {
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) },
    data: {
      project_id: project,
      spec: {
        id: entityId,
        name: name + " 单元",
        version: 1,
        type: "management_unit",
        management_unit_id: "scene-test-U1",
        crs: "EPSG:4326",
        geometry: aoi.geometry,
        valid_from: "2020-01-01T00:00:00Z",
        valid_to: null,
        properties: { source: "synthetic browser test" },
      },
    },
  });
  expect(entity.status()).toBe(201);
  await page.goto("/scenes/new");
  await page.getByLabel("场景名称", { exact: true }).fill(name);
  await page
    .getByLabel("管理目标", { exact: true })
    .fill("验证研究范围和实体版本");
  await page
    .getByLabel("开始时间（含时区）", { exact: true })
    .fill("2020-01-01T00:00:00Z");
  await page
    .getByLabel("结束时间（含时区）", { exact: true })
    .fill("2023-01-01T00:00:00Z");
  const map = page.getByLabel("场景研究范围地图", { exact: true });
  await expect(map).toHaveAttribute("data-loaded", "true");
  await page.getByRole("button", { name: "开始绘制 AOI", exact: true }).click();
  const canvas = map.locator("canvas");
  for (const point of [
    { x: 250, y: 120 },
    { x: 380, y: 120 },
    { x: 380, y: 230 },
  ])
    await canvas.click({ position: point });
  await expect(page.getByText(/已选择 3 个顶点/)).toBeVisible();
  await page.getByRole("button", { name: "完成 AOI", exact: true }).click();
  const drawingCheck = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/scene-drafts/inspect"),
  );
  await page
    .getByRole("button", { name: "检查场景与数据覆盖", exact: true })
    .click();
  const drawn = await drawingCheck;
  expect(drawn.status()).toBe(200);
  expect((await drawn.json()).study_area_wgs84.type).toBe("Polygon");
  await page
    .getByLabel("上传 AOI（WGS 84 GeoJSON）", { exact: true })
    .setInputFiles({
      name: "aoi.geojson",
      mimeType: "application/geo+json",
      buffer: Buffer.from(JSON.stringify(aoi)),
    });
  await page
    .getByRole("checkbox", { name: name + " 单元 · v1", exact: true })
    .check();
  await page
    .getByLabel("实体类型（逗号分隔）", { exact: true })
    .fill("management_unit");
  await page
    .getByRole("checkbox", { name: "dem.tif · v1", exact: true })
    .check();
  const coverageEvent = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/scene-drafts/inspect"),
  );
  await page
    .getByRole("button", { name: "检查场景与数据覆盖", exact: true })
    .click();
  const coverage = await coverageEvent;
  expect(coverage.status()).toBe(200);
  const report = await coverage.json();
  expect(report.entity_coverage[0].reference).toEqual({
    id: entityId,
    version: 1,
  });
  expect(report.data_coverage).toHaveLength(1);
  expect(report.data_coverage[0].spatial_fraction).toBeGreaterThan(0.999);
  expect(report.data_coverage[0].method).toBe(
    "inspected_extent_equal_area_EPSG6933",
  );
  const saveEvent = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/scenes") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存场景版本", exact: true }).click();
  const saved = await saveEvent;
  expect(saved.status()).toBe(201);
  const scene = (await saved.json()).spec;
  expect(scene.entity_references).toEqual([{ id: entityId, version: 1 }]);
  expect(scene.study_area).toEqual(aoi.geometry);
  await expect(
    page.getByRole("heading", { name: "运行场景 v1", exact: true }),
  ).toBeVisible();
  await page.getByLabel("场景名称", { exact: true }).fill(name + " 修订");
  await expect(
    page.getByRole("button", { name: "预检所选工作流", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "保存场景版本", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "运行场景 v2", exact: true }),
  ).toBeVisible();
  const old = await page.request.get(`/api/v1/scenes/${scene.id}?version=1`);
  expect((await old.json()).spec.name).toBe(name);
  await page
    .getByRole("button", { name: "检查场景与数据覆盖", exact: true })
    .click();
  await expect(
    page.getByRole("cell", { name: "dem.tif · v1", exact: true }),
  ).toBeVisible();
  await expect(map).toHaveAttribute("data-loaded", "true");
  await page.screenshot({
    path: "../../artifacts/screenshots/scene-workspace.png",
    fullPage: true,
  });
});

test("saved scene copy preflights and executes the actual pinned coastal workflow", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const project = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const csrf = (await page.context().cookies()).find(
    (cookie) => cookie.name === "coastmas_csrf",
  )!.value;
  const units = JSON.parse(
    await readFile(
      new URL("../../../sample-data/management_units.geojson", import.meta.url),
      "utf8",
    ),
  );
  const entityId = `result-entity-${Date.now()}`;
  const entityName = `结果绑定单元 ${Date.now()}`;
  const createdEntity = await page.request.post("/api/v1/entities", {
    headers: { "X-CSRF-Token": decodeURIComponent(csrf) },
    data: {
      project_id: project,
      spec: {
        id: entityId,
        name: entityName,
        version: 1,
        type: "management_unit",
        management_unit_id: "U1",
        crs: "EPSG:4326",
        geometry: units.features.find(
          (feature: { properties: { unit_id: string } }) =>
            feature.properties.unit_id === "U1",
        ).geometry,
        valid_from: "2020-01-01T00:00:00Z",
        valid_to: null,
        properties: { source: "synthetic binding acceptance" },
      },
    },
  });
  expect(createdEntity.status()).toBe(201);
  await page.goto("/scenes");
  await page
    .getByRole("link", {
      name: "Synthetic coastal inundation screening",
      exact: true,
    })
    .click();
  await page.getByRole("link", { name: "打开场景工作台", exact: true }).click();
  await expect(page.getByLabel("基准海平面（m）", { exact: true })).toHaveValue(
    "0",
  );
  await page
    .getByLabel("场景名称", { exact: true })
    .fill(`浏览器实际执行场景 ${Date.now()}`);
  const entityChoice = page.getByRole("checkbox", {
    name: entityName + " · v1",
    exact: true,
  });
  for (let pageNumber = 0; pageNumber < 20; pageNumber++) {
    const next = page.getByRole("button", {
      name: "下一页地理实体",
      exact: true,
    });
    await expect
      .poll(
        async () =>
          (await entityChoice.count()) > 0 || (await next.isEnabled()),
      )
      .toBeTruthy();
    if (await entityChoice.count()) break;
    const loaded = page.waitForResponse((response) =>
      response.url().includes("/api/v1/entities?"),
    );
    await next.click();
    await loaded;
  }
  await entityChoice.check();
  const copyEvent = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/scenes") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "复制场景", exact: true }).click();
  const copied = await copyEvent;
  expect(copied.status()).toBe(201);
  const scene = (await copied.json()).spec;
  const selector = page.getByRole("combobox", {
    name: "执行工作流",
    exact: true,
  });
  const option = selector
    .locator("option")
    .filter({ hasText: /^coastal_impact · v1/ })
    .first();
  await selector.selectOption((await option.getAttribute("value"))!);
  await page
    .getByRole("button", { name: "预检所选工作流", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "执行所选工作流", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "执行所选工作流", exact: true })
    .click();
  await page
    .getByRole("link", { name: "查看不可变结果" })
    .click({ timeout: 90000 });
  await expect(page.getByText("80000", { exact: true })).toBeVisible();
  await expect(page.getByText("320", { exact: true })).toBeVisible();
  const event = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整结果" }).click();
  const result = JSON.parse(
    await readFile((await (await event).path())!, "utf8"),
  );
  expect(result.run_manifest.scene.id).toBe(scene.id);
  expect(result.run_manifest.scene.version).toBe(1);
  expect(result.llm_calls).toBe(0);
  expect(result.result_view.binding_status).toBe("PARTIAL");
  expect(result.result_view.entity_binding).toHaveLength(1);
  expect(result.result_view.entity_binding[0]).toMatchObject({
    geographic_entity_id: entityId,
    geographic_entity_version: 1,
    management_unit_id: "U1",
  });
  await expect(page.getByText("部分绑定", { exact: true })).toBeVisible();
  await expect(
    page.getByText(entityId + " · v1", { exact: true }),
  ).toBeVisible();
  expect(result.geographic_entities[0].id).toBe(entityId);
  expect(result.result_entity_geometries.features).toHaveLength(1);
  expect(result.result_entity_geometries.features[0].properties.entity_id).toBe(
    entityId,
  );
  const resultMap = page.getByLabel("结果绑定实体地图", { exact: true });
  await expect(resultMap).toHaveAttribute("data-loaded", "true");
  await page.getByRole("button", { name: "定位 U1", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "定位 U1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page
    .getByRole("button", { name: "显示全部绑定实体", exact: true })
    .click();
  await expect(resultMap).toHaveAttribute("data-loaded", "true");
  const layers = page.getByRole("group", {
    name: "结果绑定实体地图图层控制",
    exact: true,
  });
  await layers
    .getByRole("checkbox", { name: "显示面图层", exact: true })
    .uncheck();
  await expect(resultMap).toHaveAttribute("data-loaded", "true");
  await resultMap.locator("canvas").click();
  await expect(
    page.getByRole("button", { name: "定位 U1", exact: true }),
  ).toHaveAttribute("aria-pressed", "false");
  await layers
    .getByRole("checkbox", { name: "显示面图层", exact: true })
    .check();
  await expect(resultMap).toHaveAttribute("data-loaded", "true");
  await resultMap.locator("canvas").click();
  await expect(
    page.getByRole("button", { name: "定位 U1", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  const descriptor = await page.request.get(
    "/api/v1/results/" + page.url().split("/").at(-1),
  );
  const published = await descriptor.json();
  expect(published.manifest.result_manifest.id).toBe(published.id);
  expect(published.manifest.result_manifest.entity_binding).toEqual(
    result.result_view.entity_binding,
  );
  await page.screenshot({
    path: "../../artifacts/screenshots/result-entity-binding.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("actual temporal assessment exposes aligned period selection and numeric time series", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/workflows");
  await page
    .getByRole("link", { name: "temporal_change", exact: true })
    .first()
    .click();
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption({ label: "Synthetic assessment scenario C · v1" });
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await page
    .getByRole("link", { name: "查看不可变结果" })
    .click({ timeout: 90000 });
  await expect(
    page.getByRole("heading", { name: "多期评价与时间序列", exact: true }),
  ).toBeVisible();
  const unit = page.getByRole("combobox", {
    name: "评价管理单元",
    exact: true,
  });
  await unit.selectOption({ label: "U1" });
  await page
    .getByRole("combobox", { name: "查看评价年份", exact: true })
    .selectOption({ label: "2022" });
  const table = page.getByRole("table", { name: "所选年份评价结果" });
  await expect(table.getByRole("row")).toHaveCount(2);
  await expect
    .poll(async () =>
      Number(
        await table
          .getByRole("row")
          .nth(1)
          .getByRole("cell")
          .nth(2)
          .textContent(),
      ),
    )
    .toBeCloseTo(0.4, 12);
  await expect(
    page.getByRole("img", { name: "U1，单位：1", exact: true }).locator("svg"),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "查看评价年份", exact: true })
    .selectOption({ label: "2020" });
  await expect
    .poll(async () =>
      Number(
        await table
          .getByRole("row")
          .nth(1)
          .getByRole("cell")
          .nth(2)
          .textContent(),
      ),
    )
    .toBeCloseTo(0.2, 12);
  await page.screenshot({
    path: "../../artifacts/screenshots/temporal-results.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("compares real baseline and raised sea-level results without overwriting either", async ({
  page,
}) => {
  test.setTimeout(150000);
  const project = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const csrf = decodeURIComponent(
    (await page.context().cookies()).find(
      (cookie) => cookie.name === "coastmas_csrf",
    )!.value,
  );
  const headers = { "X-CSRF-Token": csrf };
  const catalog = await page.request.get(
    `/api/v1/workflows?project_id=${encodeURIComponent(project)}&limit=500`,
  );
  expect(catalog.status()).toBe(200);
  const entry = (await catalog.json()).find(
    (item: { name: string }) => item.name === "coastal_impact",
  );
  expect(entry).toBeTruthy();
  const originalResponse = await page.request.get(
    `/api/v1/workflows/${encodeURIComponent(entry.id)}?version=${entry.version}`,
  );
  const original = (await originalResponse.json()).spec;
  const baseline = structuredClone(original);
  baseline.id = `comparison-baseline-${Date.now()}`;
  baseline.name = `比较基准 ${Date.now()}`;
  baseline.version = 1;
  baseline.nodes.find(
    (node: { id: string }) => node.id === "screening",
  ).parameters.increment = 0;
  const saved = await page.request.post("/api/v1/workflows", {
    headers,
    data: { project_id: project, spec: baseline },
  });
  expect(saved.status()).toBe(201);
  const sceneResponse = await page.request.get(
    `/api/v1/scenes?project_id=${encodeURIComponent(project)}&limit=500`,
  );
  const scene = (await sceneResponse.json()).find(
    (item: { name: string }) =>
      item.name === "Synthetic coastal inundation screening",
  );
  expect(scene).toBeTruthy();
  const resultIds: string[] = [];
  for (const workflow of [original, baseline]) {
    const submitted = await page.request.post(
      `/api/v1/workflows/${encodeURIComponent(workflow.id)}/run`,
      {
        headers: { ...headers, "Idempotency-Key": crypto.randomUUID() },
        data: {
          workflow_version: workflow.version,
          scene_id: scene.id,
          scene_version: scene.version,
          random_seed: 42,
        },
      },
    );
    expect(submitted.status()).toBe(202);
    const jobId = (await submitted.json()).id;
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/v1/jobs/${jobId}`)).json())
            .status,
        { timeout: 90000, intervals: [500, 1000] },
      )
      .toBe("SUCCEEDED");
    const results = await page.request.get(
      `/api/v1/results?project_id=${encodeURIComponent(project)}&limit=50`,
    );
    const result = (await results.json()).find(
      (item: { job_id: string }) => item.job_id === jobId,
    );
    expect(result).toBeTruthy();
    resultIds.push(result.id);
  }
  await page.goto("/results");
  for (const id of resultIds)
    await page
      .getByRole("checkbox", { name: `选择对比 ${id}`, exact: true })
      .check();
  await page.getByRole("link", { name: "比较所选结果", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "场景结果比较", exact: true }),
  ).toBeVisible();
  const left = page.getByRole("region", { name: "左侧原始输出", exact: true });
  const right = page.getByRole("region", { name: "右侧原始输出", exact: true });
  await expect(left.getByText("80000", { exact: true })).toBeVisible();
  await expect(left.getByText("320", { exact: true })).toBeVisible();
  await expect(right.getByText("40000", { exact: true }).first()).toBeVisible();
  await expect(right.getByText("160", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("table", { name: "管理指标对照表", exact: true }),
  ).toBeVisible();
  await expect(
    left.getByLabel("分析结果地图", { exact: true }),
  ).toHaveAttribute("data-loaded", "true");
  await expect(
    right.getByLabel("分析结果地图", { exact: true }),
  ).toHaveAttribute("data-loaded", "true");
  for (const [index, id] of resultIds.entries()) {
    const result = await page.request.get(`/api/v1/results/${id}/content`);
    expect(
      (await result.json()).outputs["statistics.statistics"]
        .estimated_affected_population,
    ).toBe(index === 0 ? 320 : 160);
  }
  await page.screenshot({
    path: "../../artifacts/screenshots/result-comparison.png",
    fullPage: true,
  });
});
