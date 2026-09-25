import { mkdir, readFile, writeFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

test("real PRD raster assets through sampled PPCI workflow and downloadable mapped result", async ({
  page,
}) => {
  test.setTimeout(600000);
  if (
    !process.env.COASTMAS_E2E_BUSINESS_ROOT ||
    !process.env.COASTMAS_PROJECTION_RELEASE
  )
    throw new Error("Actual business root and verified R release required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  const project = await page.locator("#project-select").inputValue();
  const csrf = (await page.context().cookies()).find(
    (item) => item.name === "coastmas_csrf",
  )!.value;
  const headers = { "X-CSRF-Token": csrf };
  const inventory = await (
    await page.request.get(
      `/api/v1/data-assets/local-files?project_id=${project}&source=business-acceptance&limit=500`,
    )
  ).json();
  const files = inventory.files.filter(
    (item: { path: string }) =>
      item.path.startsWith("zhusanjiao/") && item.path.endsWith(".tif"),
  );
  expect(files).toHaveLength(4);
  const assets = [];
  for (const [index, file] of files.entries()) {
    const imported = await page.request.post(
      "/api/v1/data-assets/ingest-local",
      {
        headers,
        timeout: 180000,
        data: {
          project_id: project,
          source: "business-acceptance",
          path: file.path,
          declaration: {
            name: `PRD真实距离${index + 1}`,
            source: "开放网站（用户声明）",
            license: "非商业（用户声明）",
            year: 2022,
          },
        },
      },
    );
    expect(imported.status(), await imported.text()).toBe(201);
    const asset = (await imported.json()).spec;
    expect(asset.quality.size_bytes).toBeGreaterThan(390 * 1024 ** 2);
    assets.push(asset);
  }
  await page.goto("/data/prepare");
  for (let index = 0; index < assets.length; index++) {
    await page
      .getByRole("button", { name: `选择PRD真实距离${index + 1}`, exact: true })
      .click();
    await page
      .getByLabel("变量名称", { exact: true })
      .nth(index)
      .fill(`distance_${index + 1}`);
    await page.getByLabel("变量单位", { exact: true }).nth(index).fill("m");
  }
  await page
    .getByLabel("输入资产名称", { exact: true })
    .fill("珠三角真实距离样本（工程验收，不作正式分区）");
  await page.getByLabel("数据范围", { exact: true }).selectOption("sample");
  await page.getByLabel("样本数量上限", { exact: true }).fill("400");
  await page.getByLabel("模型运行时按所选样本均值和标准差标准化").check();
  await page.getByLabel("统计时期开始", { exact: true }).fill("2022-01-01");
  await page.getByLabel("统计时期结束", { exact: true }).fill("2023-01-01");
  await page.getByLabel("时间支持长度", { exact: true }).fill("365 day");
  const folder = `../../artifacts/projection-workflow/${Date.now()}`;
  await mkdir(folder, { recursive: true });
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(viewport.width + 1);
    await page.screenshot({
      path: `${folder}/prepare-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const pending = page.waitForResponse(
    (response) =>
      response.url().endsWith("/prepare-raster-frame") &&
      response.request().method() === "POST",
    { timeout: 300000 },
  );
  await page
    .getByRole("button", { name: "生成可用于模型的输入资产", exact: true })
    .click();
  const preparedResponse = await pending;
  expect(preparedResponse.status(), await preparedResponse.text()).toBe(201);
  const prepared = (await preparedResponse.json()).spec;
  const data = await (
    await page.request.get(
      `/api/v1/data-assets/${encodeURIComponent(prepared.id)}/download`,
    )
  ).json();
  expect(data.frame.row_ids).toHaveLength(400);
  expect(data.quality.joint_valid_cells).toBeGreaterThan(400);
  expect(data.quality.total_cells).toBe(11416 * 9000);
  expect(
    prepared.quality.lineage.map((item: { checksum: string }) => item.checksum),
  ).toEqual(assets.map((item) => item.checksum));
  // Explicit test-only references verify conversion, never define business weights.
  const frameworkId = `prd-technical-framework-${Date.now()}`;
  const definition = await page.request.post("/api/v1/indicator-frameworks", {
    headers,
    data: {
      project_id: project,
      spec: {
        id: frameworkId,
        name: "真实距离转换工程验收（非业务评价体系）",
        version: 1,
        description:
          "Isolated technical unit-conversion fixture; no business directions inferred",
        demo: true,
        spatial_support: "grid",
        indicators: [
          {
            indicator_id: "distance_km",
            name: "距离千米转换验证",
            category: "Resource",
            unit: "km",
            direction: "positive",
            source: { x: "distance_1" },
            formula: "x",
            normalization: { method: "fixed_minmax", lower: 0, upper: 1000 },
            weight_method: "manual",
            weight: 1,
          },
        ],
      },
    },
  });
  expect(definition.status(), await definition.text()).toBe(201);
  await page.goto(`/assessments/${frameworkId}`);
  await page
    .getByRole("combobox", { name: "观测数据", exact: true })
    .selectOption(prepared.id);
  const preparedIndicators = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/indicator-frameworks/${frameworkId}/prepare`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "准备固定版本输入", exact: true })
    .click();
  const indicatorResponse = await preparedIndicators;
  expect(indicatorResponse.status(), await indicatorResponse.text()).toBe(201);
  const indicatorAsset = (await indicatorResponse.json()).spec;
  const indicatorData = await (
    await page.request.get(`/api/v1/data-assets/${indicatorAsset.id}/download`)
  ).json();
  expect(indicatorAsset.quality.scope).toBe("sample_only");
  expect(indicatorAsset.quality.business_validated).toBe(false);
  expect(indicatorData.frame.unit_ids).toEqual(data.frame.row_ids);
  expect(indicatorData.locations).toEqual(data.locations);
  for (let index = 0; index < 400; index++)
    expect(indicatorData.frame.values[index][0]).toBeCloseTo(
      data.frame.values[index][0] / 1000,
      8,
    );
  await expect(
    page.getByRole("link", { name: "查看实际文件与质量", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${folder}/assessment-bridge-1440.png`,
    fullPage: true,
  });
  await writeFile(
    `${folder}/assessment-bridge.json`,
    JSON.stringify(
      {
        scope: "technical_conversion_only_not_approved_business_framework",
        source: prepared.id,
        derived: indicatorAsset,
        tested_rows: 400,
        maximum_unit_conversion_error: Math.max(
          ...indicatorData.frame.values.map((row: number[], index: number) =>
            Math.abs(row[0] - data.frame.values[index][0] / 1000),
          ),
        ),
      },
      null,
      2,
    ),
  );
  await page.goto("/models/new");
  await page
    .getByRole("button", { name: "登记PPCI 投影寻踪聚类", exact: true })
    .click();
  await page
    .getByRole("button", { name: "批准此版本运行适配器", exact: true })
    .click();
  await expect(
    page.getByText("运行适配器已审批；输入映射与工作流科学预检仍必须通过。", {
      exact: true,
    }),
  ).toBeVisible();
  const modelId = `business:${project}:ppci_mcdc`;
  const model = (
    await (
      await page.request.get(`/api/v1/models/${encodeURIComponent(modelId)}`)
    ).json()
  ).spec;
  expect(model.execution_status).toBe("EXECUTABLE");
  const xs = data.locations.map((item: number[]) => item[0]);
  const ys = data.locations.map((item: number[]) => item[1]);
  const [west, east, south, north] = [
    Math.min(...xs),
    Math.max(...xs),
    Math.min(...ys),
    Math.max(...ys),
  ];
  const scene = {
    id: `prd-scene-${Date.now()}`,
    name: "真实PRD样本技术执行",
    version: 1,
    management_goal: "ppci_mcdc",
    study_area: {
      type: "Polygon",
      coordinates: [
        [
          [west, south],
          [east, south],
          [east, north],
          [west, north],
          [west, south],
        ],
      ],
    },
    entity_types: ["observation"],
    time_range: { start: "2022-01-01T00:00:00Z", end: "2023-01-01T00:00:00Z" },
    scenario_conditions: {},
    constraints: [],
    required_outputs: ["result"],
    data_policy: { study_area_crs: "EPSG:4326" },
    quality_requirements: {},
  };
  const sceneCreated = await page.request.post("/api/v1/scenes", {
    headers,
    data: { project_id: project, spec: scene },
  });
  expect(sceneCreated.status(), await sceneCreated.text()).toBe(201);
  const workflow = {
    id: `prd-workflow-${Date.now()}`,
    name: "真实距离投影寻踪聚类（仅样本）",
    version: 1,
    scene_type: "custom",
    nodes: [
      {
        id: "cluster",
        model_id: modelId,
        model_version: model.version,
        parameters: { clusters: 3, seed: 42 },
      },
    ],
    edges: [],
    input_bindings: [
      {
        source: { id: prepared.id, version: prepared.version },
        target: { node_id: "cluster", variable: "frame" },
        semantic_mapping: "exact_standard_name",
        unit_conversion: null,
        crs_transform: null,
        resampling: null,
        temporal_transform: null,
        quality_check: [],
        status: "VALIDATED",
      },
    ],
    parameter_bindings: [],
    constraints: [],
    validation_rules: [],
    execution_policy: { timeout_seconds: 180, max_retries: 0 },
    output_definition: [{ node_id: "cluster", variable: "result" }],
  };
  const created = await page.request.post("/api/v1/workflows", {
    headers,
    data: { project_id: project, spec: workflow },
  });
  expect(created.status(), await created.text()).toBe(201);
  await page.goto(`/workflows/${encodeURIComponent(workflow.id)}`);
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption({ label: "真实PRD样本技术执行 · v1" });
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await page
    .getByRole("link", { name: "查看不可变结果", exact: true })
    .click({ timeout: 180000 });
  await expect(
    page.getByText("仅样本结果，不代表全图分类或全图预测。", { exact: false }),
  ).toBeVisible();
  await expect(page.locator(".geographic-map").first()).toHaveAttribute(
    "data-loaded",
    "true",
  );
  await page.getByRole("button", { name: "下一页观测", exact: true }).click();
  await expect(
    page.getByText("第2页 / 20页 · 共400项", { exact: true }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整结果", exact: true }).click();
  const download = await downloadPromise;
  const output = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(output.executed_nodes).toEqual(["cluster"]);
  expect(output.outputs["cluster.result"].cluster).toHaveLength(400);
  expect(output.outputs["cluster.result"].row_ids).toEqual(data.frame.row_ids);
  expect(output.outputs["cluster.result"].locations).toEqual(data.locations);
  expect(output.outputs["cluster.result"].business_validated).toBe(false);
  expect(output.llm_calls).toBe(0);
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(viewport.width + 1);
    await page.screenshot({
      path: `${folder}/result-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await writeFile(
    `${folder}/result.json`,
    JSON.stringify(
      {
        scope: "real_PRD_explicit_sample_engineering_not_business_zoning",
        assets,
        prepared,
        result: output,
      },
      null,
      2,
    ),
  );
  // A response is selected solely to exercise the provided regression end to end.
  // It is not an endorsed business target or independent predictive validation.
  const regressionResponse = await page.request.post(
    "/api/v1/data-assets/prepare-raster-frame",
    {
      headers,
      timeout: 300000,
      data: {
        project_id: project,
        name: "真实距离回归工程验证（非业务目标）",
        features: assets.map((asset, index) => ({
          asset_id: asset.id,
          version: asset.version,
          name: `distance_${index + 1}`,
          unit: "m",
          band: 1,
        })),
        options: {
          mode: "sample",
          sample_size: 400,
          seed: 42,
          standardize: true,
          response_index: 0,
        },
        period: scene.time_range,
        time_resolution: "365 day",
      },
    },
  );
  expect(regressionResponse.status(), await regressionResponse.text()).toBe(
    201,
  );
  const regressionAsset = (await regressionResponse.json()).spec;
  const regressionInput = await (
    await page.request.get(`/api/v1/data-assets/${regressionAsset.id}/download`)
  ).json();
  expect(regressionInput.frame.row_ids).toEqual(data.frame.row_ids);
  expect(regressionInput.frame.feature_names).not.toContain("distance_1");
  expect(regressionInput.frame.response).toEqual(
    data.frame.values.map((row: number[]) => row[0]),
  );
  await page.goto("/models/new");
  await page
    .getByRole("button", { name: "登记pprRFA 投影寻踪回归", exact: true })
    .click();
  await page
    .getByRole("button", { name: "批准此版本运行适配器", exact: true })
    .click();
  await expect(
    page.getByText("运行适配器已审批；输入映射与工作流科学预检仍必须通过。", {
      exact: true,
    }),
  ).toBeVisible();
  const regressionModelId = `business:${project}:ppr_ols`;
  const regressionModel = (
    await (
      await page.request.get(
        `/api/v1/models/${encodeURIComponent(regressionModelId)}`,
      )
    ).json()
  ).spec;
  const regressionWorkflow = {
    ...workflow,
    id: `prd-regression-${Date.now()}`,
    name: "真实距离回归工程验证",
    nodes: [
      {
        id: "regress",
        model_id: regressionModelId,
        model_version: regressionModel.version,
        parameters: { terms: 2, seed: 42 },
      },
    ],
    input_bindings: [
      {
        ...workflow.input_bindings[0],
        source: { id: regressionAsset.id, version: regressionAsset.version },
        target: { node_id: "regress", variable: "frame" },
      },
    ],
    output_definition: [{ node_id: "regress", variable: "result" }],
  };
  const regressionCreated = await page.request.post("/api/v1/workflows", {
    headers,
    data: { project_id: project, spec: regressionWorkflow },
  });
  expect(regressionCreated.status(), await regressionCreated.text()).toBe(201);
  await page.goto(`/workflows/${regressionWorkflow.id}`);
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption(scene.id);
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await page
    .getByRole("link", { name: "查看不可变结果", exact: true })
    .click({ timeout: 180000 });
  await expect(
    page.getByText("回归为训练样本拟合", { exact: false }),
  ).toBeVisible();
  const regressionDownload = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整结果", exact: true }).click();
  const regressionFile = await regressionDownload;
  const regressionOutput = JSON.parse(
    await readFile((await regressionFile.path())!, "utf8"),
  );
  const fitted = regressionOutput.outputs["regress.result"];
  expect(fitted.row_ids).toEqual(regressionInput.frame.row_ids);
  expect(fitted.locations).toEqual(regressionInput.locations);
  expect(fitted.fitted).toHaveLength(400);
  expect(fitted.prediction_scope).toBe("training_fit_not_external_validation");
  expect(fitted.business_validated).toBe(false);
  expect(regressionOutput.llm_calls).toBe(0);
  for (let index = 0; index < 400; index++) {
    expect(Number.isFinite(fitted.fitted[index])).toBe(true);
    expect(fitted.residuals[index]).toBeCloseTo(
      regressionInput.frame.response[index] - fitted.fitted[index],
      7,
    );
  }
  await expect(page.locator(".geographic-map").first()).toHaveAttribute(
    "data-loaded",
    "true",
  );
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1366, height: 768 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(viewport.width + 1);
    await expect
      .poll(() =>
        page
          .locator(".geographic-map canvas")
          .first()
          .evaluate((element) => {
            const canvas = element as HTMLCanvasElement;
            return Math.abs(
              canvas.width -
                canvas.getBoundingClientRect().width * window.devicePixelRatio,
            );
          }),
      )
      .toBeLessThanOrEqual(1);
    await expect(page.locator(".geographic-map").first()).toHaveAttribute(
      "data-loaded",
      "true",
    );
    await page.screenshot({
      path: `${folder}/regression-${viewport.width}.png`,
      fullPage: true,
    });
  }
  await writeFile(
    `${folder}/regression.json`,
    JSON.stringify(
      {
        scope: "real_PRD_engineering_regression_only_not_business_target",
        prepared: regressionAsset,
        result: regressionOutput,
      },
      null,
      2,
    ),
  );
});
