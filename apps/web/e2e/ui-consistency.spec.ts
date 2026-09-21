import { mkdir, readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";

const phase = process.env.COASTMAS_UI_PHASE ?? "after";
const root = `../../artifacts/ui-consistency/${phase}`;
const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 900 },
  { width: 390, height: 844 },
];
const layout: unknown[] = [];
async function capture(page: Page, name: string) {
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `${root}/${name}-${viewport.width}.png` });
    const measured = await page.evaluate(() => ({
      width: innerWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    layout.push({ name, ...measured });
    if (phase === "after")
      expect(
        measured.scroll,
        `${name} ${viewport.width}: whole-page overflow`,
      ).toBeLessThanOrEqual(measured.width + 1);
  }
  await page.setViewportSize(viewports[0]!);
}

test("representative UI screenshots and unchanged scientific submission semantics", async ({
  page,
}) => {
  test.setTimeout(180000);
  await mkdir(root, { recursive: true });
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  const loginResponse = page.waitForResponse(
    (r) => r.url().endsWith("/auth/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const csrf = (await (await loginResponse).json()).csrf_token;
  await expect(page.getByRole("combobox", { name: "当前项目" })).toBeVisible();
  const originalProject = await page
    .getByRole("combobox", { name: "当前项目" })
    .inputValue();
  const originalScenes = await (
    await page.request.get(`/api/v1/scenes?project_id=${originalProject}`)
  ).json();
  const source = (
    await (
      await page.request.get(`/api/v1/scenes/${originalScenes[0].id}`)
    ).json()
  ).spec;
  const created = await page.request.post("/api/v1/projects", {
    headers: { "X-CSRF-Token": csrf },
    data: { name: "UI consistency isolated fixtures" },
  });
  expect(created.status()).toBe(201);
  const project = (await created.json()).id;
  const scene = {
    ...source,
    id: randomUUID(),
    version: 1,
    name: "UI验收研究区",
    entity_references: [],
    data_references: [],
  };
  const savedScene = await page.request.post("/api/v1/scenes", {
    headers: { "X-CSRF-Token": csrf },
    data: { project_id: project, spec: scene },
  });
  expect(savedScene.status()).toBe(201);
  await page.reload();
  await page.getByRole("combobox", { name: "当前项目" }).selectOption(project);
  if (
    (await page
      .getByRole("button", { name: "评价与协同", exact: true })
      .getAttribute("aria-expanded")) === "false"
  )
    await page.getByRole("button", { name: "评价与协同", exact: true }).click();
  await page.getByRole("link", { name: "协同方案", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "新建方案", exact: true }),
  ).toBeEnabled();
  await expect(page.getByRole("status")).toHaveCount(0);
  if (phase === "after")
    await expect(page.getByText("暂无协同方案", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "上一页", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "下一页", exact: true }),
  ).toBeDisabled();
  await capture(page, "collaboration-empty");
  await page.getByRole("button", { name: "新建方案", exact: true }).click();
  await page.getByLabel("方案名称", { exact: true }).fill("UI验收方案");
  await page
    .getByLabel("依据与意见", { exact: true })
    .fill("独立测试数据；保留原有提交语义。");
  await page
    .getByRole("combobox", { name: "固定场景", exact: true })
    .selectOption(JSON.stringify([scene.id, 1]));
  await page.getByRole("button", { name: "添加目标", exact: true }).click();
  await page.getByLabel("目标标识 1", { exact: true }).fill("ui-goal");
  await page.getByLabel("目标名称 1", { exact: true }).fill("生态目标");
  await page.getByLabel("目标权重 1", { exact: true }).fill("1");
  await capture(page, "collaboration-form");
  const proposalResponse = page.waitForResponse(
    (r) => r.url().endsWith("/proposals") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存方案版本", exact: true }).click();
  const proposal = await proposalResponse;
  expect(proposal.status()).toBe(201);
  const proposalBody = proposal.request().postDataJSON();
  await page.goto("/collaboration");
  await page.getByRole("combobox", { name: "当前项目" }).selectOption(project);
  await expect(page.getByText("UI验收方案", { exact: true })).toBeVisible();
  await page
    .getByRole("checkbox", { name: "选择比较 UI验收方案", exact: true })
    .check();
  await expect(
    page.getByRole("button", { name: "比较所选版本（1）", exact: true }),
  ).toBeEnabled();
  await capture(page, "collaboration-populated");
  await page.getByRole("button", { name: "清除比较", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "选择比较 UI验收方案", exact: true }),
  ).not.toBeChecked();
  await page.getByRole("link", { name: "时间适配", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "保存时间适配工作流", exact: true }),
  ).toBeDisabled();
  await capture(page, "temporal-empty");
  await page
    .getByRole("combobox", { name: "沿用研究区的场景", exact: true })
    .selectOption(scene.id);
  for (const [label, value] of [
    ["名称", "UI时间适配"],
    ["数据来源", "SYNTHETIC isolated UI test"],
    ["许可证", "CC0"],
    ["物理变量", "air_temperature"],
    ["输入单位", "degC"],
    ["输出单位", "kelvin"],
    ["目标开始时间", "2025-01-01T00:00:00Z"],
    ["目标结束时间", "2025-01-01T04:00:00Z"],
    ["观测1开始", "2025-01-01T00:00:00Z"],
    ["观测1结束", "2025-01-01T01:00:00Z"],
    ["观测1数值", "0"],
  ])
    await page.getByLabel(label!, { exact: true }).fill(value!);
  await page.getByRole("button", { name: "添加观测", exact: true }).click();
  await page
    .getByLabel("观测2开始", { exact: true })
    .fill("2025-01-01T01:00:00Z");
  await page
    .getByLabel("观测2结束", { exact: true })
    .fill("2025-01-01T04:00:00Z");
  // Deliberately keep the second value empty: unchanged null propagation is a business invariant.
  await page.getByLabel("名称", { exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("数据来源", { exact: true })).toBeFocused();
  await capture(page, "temporal-filled");
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page
      .getByRole("button", { name: "保存时间适配工作流", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `${root}/temporal-observations-${viewport.width}.png`,
    });
  }
  const temporalResponse = page.waitForResponse(
    (r) =>
      r.url().endsWith("/adaptations/temporal") &&
      r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "保存时间适配工作流", exact: true })
    .click();
  const temporal = await temporalResponse;
  expect(temporal.status()).toBe(201);
  const temporalBody = temporal.request().postDataJSON();
  expect(
    temporalBody.request.observations.map(
      (row: { value: number | null }) => row.value,
    ),
  ).toEqual([0, null]);
  const canonical = {
    proposal: {
      ...proposalBody,
      project_id: "<PROJECT>",
      spec: {
        ...proposalBody.spec,
        id: "<NEW>",
        scene: { id: "<SCENE>", version: 1 },
      },
    },
    temporal: {
      ...temporalBody,
      project_id: "<PROJECT>",
      idempotency_key: "<KEY>",
      scene: { id: "<SCENE>", version: 1 },
    },
  };
  await writeFile(`${root}/requests.json`, JSON.stringify(canonical, null, 2));
  await writeFile(`${root}/layout.json`, JSON.stringify(layout, null, 2));
  if (phase === "after")
    expect(canonical).toEqual(
      JSON.parse(
        await readFile(
          "../../artifacts/ui-consistency/before/requests.json",
          "utf8",
        ),
      ),
    );
  if (phase === "after") {
    await page.setViewportSize(viewports[0]!);
    // Real, isolated records exercise the existing 50-row paging and 20-selection limit.
    for (let start = 0; start < 50; start += 10) {
      const responses = await Promise.all(
        Array.from({ length: 10 }, (_, index) =>
          page.request.post("/api/v1/proposals", {
            headers: { "X-CSRF-Token": csrf },
            data: {
              ...proposalBody,
              spec: {
                ...proposalBody.spec,
                id: randomUUID(),
                name: `UI分页方案 ${start + index}`,
              },
            },
          }),
        ),
      );
      for (const response of responses) expect(response.status()).toBe(201);
    }
    await page.goto("/collaboration");
    await page
      .getByRole("combobox", { name: "当前项目" })
      .selectOption(project);
    await expect(page.locator("tbody tr")).toHaveCount(50);
    const first = page.getByRole("checkbox").first();
    const firstLabel = await first.getAttribute("aria-label");
    await first.check();
    await page.getByRole("button", { name: "下一页", exact: true }).click();
    await expect(page.locator("tbody tr")).toHaveCount(1);
    await page.getByRole("checkbox").check();
    await expect(
      page.getByRole("button", { name: "比较所选版本（2）", exact: true }),
    ).toBeEnabled();
    const comparison = page.waitForResponse(
      (r) =>
        r.url().endsWith("/proposals/compare") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "比较所选版本（2）", exact: true })
      .click();
    const compared = await comparison;
    expect(compared.status()).toBe(200);
    const comparedBody = compared.request().postDataJSON();
    expect(comparedBody.project_id).toBe(project);
    expect(comparedBody.proposals).toHaveLength(2);
    expect(
      new Set(comparedBody.proposals.map((p: { id: string }) => p.id)).size,
    ).toBe(2);
    await page.getByRole("button", { name: "上一页", exact: true }).click();
    await expect(
      page.getByRole("checkbox", { name: firstLabel!, exact: true }),
    ).toBeChecked();
    await page.getByRole("button", { name: "清除比较", exact: true }).click();
    for (let index = 0; index < 21; index++)
      await page.getByRole("checkbox").nth(index).check();
    await expect(
      page.getByRole("button", { name: "比较所选版本（21）", exact: true }),
    ).toBeDisabled();
    await page.getByRole("button", { name: "清除比较", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "比较所选版本（0）", exact: true }),
    ).toBeDisabled();
    // A failed list must not be presented as an empty successful list.
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v1/proposals?**", async (route) => {
      await gate;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          error_code: "UI_TEST_UNAVAILABLE",
          message: "隔离验收：服务暂不可用",
        }),
      });
    });
    await page.goto("/collaboration");
    await expect(page.getByRole("status")).toContainText("正在读取数据");
    await expect(page.getByText("暂无协同方案", { exact: true })).toHaveCount(
      0,
    );
    release();
    await expect(page.getByRole("alert")).toContainText("UI_TEST_UNAVAILABLE", {
      timeout: 20000,
    });
    await expect(page.getByText("暂无协同方案", { exact: true })).toHaveCount(
      0,
    );
    await page.screenshot({ path: `${root}/collaboration-request-error.png` });
    await page.unrouteAll({ behavior: "wait" });
    await page.goto("/temporal");
    await page
      .getByRole("combobox", { name: "当前项目" })
      .selectOption(project);
    await page
      .getByRole("combobox", { name: "沿用研究区的场景", exact: true })
      .selectOption(scene.id);
    await page
      .getByRole("button", { name: "保存时间适配工作流", exact: true })
      .click();
    await expect(page.getByRole("alert")).toBeVisible();
    await page.screenshot({ path: `${root}/temporal-validation-error.png` });
  }
});
