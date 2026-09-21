import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("spatial optimization executes actual feasible and infeasible cases with pinned geometry", async ({
  page,
}) => {
  test.setTimeout(180000);
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8")),
    );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  const project = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const csrf = decodeURIComponent(
    (await page.context().cookies()).find((c) => c.name === "coastmas_csrf")!
      .value,
  );
  const geometries = JSON.parse(
    await readFile(
      new URL("../../../sample-data/management_units.geojson", import.meta.url),
      "utf8",
    ),
  );
  const references = [];
  const suffix = Date.now();
  for (let index = 1; index <= 3; index++) {
    const id = `optimization-entity-${suffix}-${index}`;
    const response = await page.request.post("/api/v1/entities", {
      headers: { "X-CSRF-Token": csrf },
      data: {
        project_id: project,
        spec: {
          id,
          name: `SYNTHETIC optimization U${index}`,
          version: 1,
          type: "management_unit",
          management_unit_id: `U${index}`,
          crs: "EPSG:4326",
          geometry: geometries.features.find(
            (f: { properties: { unit_id: string } }) =>
              f.properties.unit_id === `U${index}`,
          ).geometry,
          valid_from: "2020-01-01T00:00:00Z",
          valid_to: null,
          properties: { source: "SYNTHETIC optimization acceptance" },
        },
      },
    });
    expect(response.status()).toBe(201);
    references.push({ id, version: 1 });
  }
  const baseResponse = await page.request.get(
    `/api/v1/scenes/${encodeURIComponent(`sample:${project}:scene-B`)}`,
  );
  expect(baseResponse.status()).toBe(200);
  const base = (await baseResponse.json()).spec;
  const sceneName = `SYNTHETIC optimization scene ${suffix}`;
  const sceneResponse = await page.request.post("/api/v1/scenes", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      project_id: project,
      spec: {
        ...base,
        id: `optimization-scene-${suffix}`,
        name: sceneName,
        version: 1,
        entity_references: references,
      },
    },
  });
  expect(sceneResponse.status()).toBe(201);
  if (
    (await page
      .getByRole("button", { name: "评价与协同", exact: true })
      .getAttribute("aria-expanded")) === "false"
  )
    await page.getByRole("button", { name: "评价与协同", exact: true }).click();
  await page.getByRole("link", { name: "空间优化", exact: true }).click();
  for (const [budget, status] of [
    ["3", "OPTIMAL"],
    ["0", "INFEASIBLE"],
  ] as const) {
    await page.getByRole("link", { name: "新建优化配置", exact: true }).click();
    await page
      .getByRole("button", { name: "载入合成示范", exact: true })
      .click();
    await page
      .getByLabel("优化名称", { exact: true })
      .fill(`SYNTHETIC ${status} ${suffix}`);
    await page
      .getByRole("combobox", { name: "基础场景", exact: true })
      .selectOption({ label: `${sceneName} · v1` });
    await page.getByLabel("预算上限", { exact: true }).fill(budget);
    await page.getByLabel("最低面积", { exact: true }).fill("4");
    for (let index = 1; index <= 3; index++) {
      await page
        .getByLabel(`候选标识 ${index}`, { exact: true })
        .fill(`U${index}`);
      await page.getByLabel(`候选面积 ${index}`, { exact: true }).fill("4");
    }
    await page
      .getByRole("button", { name: "保存固定优化配置", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "优化配置与结果", exact: true }),
    ).toBeVisible();
    const recordUrl = page.url();
    await page.getByRole("button", { name: "科学预检", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "提交优化运行", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("button", { name: "提交优化运行", exact: true })
      .click();
    await page
      .getByRole("link", { name: "查看不可变结果" })
      .click({ timeout: 90000 });
    const resultId = decodeURIComponent(
      new URL(page.url()).pathname.split("/").at(-1)!,
    );
    const resultResponse = await page.request.get(
      `/api/v1/results/${encodeURIComponent(resultId)}/content`,
    );
    expect(resultResponse.status()).toBe(200);
    const result = await resultResponse.json();
    const outcome = result.outputs["optimize.allocation"];
    expect(outcome.status).toBe(status);
    expect(outcome.selected).toEqual(status === "OPTIMAL" ? ["U3"] : []);
    expect(outcome.policy_decision).toBe(false);
    expect(outcome.totals?.area ?? null).toBe(
      status === "OPTIMAL" ? 40000 : null,
    );
    expect(result.result_view.binding_status).toBe("BOUND");
    expect(result.result_view.entity_binding).toHaveLength(3);
    await page.goto(recordUrl);
    await expect(
      page.getByText(`优化状态：${status}`, { exact: true }),
    ).toBeVisible();
    if (status === "INFEASIBLE")
      await expect(
        page.getByText("没有可行分配，不把空结果解释为全部未选中。", {
          exact: true,
        }),
      ).toBeVisible();
    await page.screenshot({
      path: `../../artifacts/screenshots/optimization-${status.toLowerCase()}.png`,
      fullPage: true,
    });
    if (
      (await page
        .getByRole("button", { name: "评价与协同", exact: true })
        .getAttribute("aria-expanded")) === "false"
    )
      await page
        .getByRole("button", { name: "评价与协同", exact: true })
        .click();
    await page.getByRole("link", { name: "空间优化", exact: true }).click();
  }
});
