import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(12),
});
test("real session, seeded catalog, deep link and logout", async ({ page }) => {
  const credentials = credentialsSchema.parse(
    JSON.parse(
      await readFile(
        new URL("../../../artifacts/runtime/demo-access.json", import.meta.url),
        "utf8",
      ),
    ),
  );
  const browserErrors: string[] = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "当前项目" }),
  ).not.toHaveValue("");
  const readiness = await page.request.get("/health/ready");
  expect(readiness.status()).toBe(200);
  expect((await readiness.json()).dependencies.object_storage).toBe("ready");
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "模型中心" })
    .click();
  const currentProject = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const modelResponse = await page.request.get(
    `/api/v1/models?project_id=${encodeURIComponent(currentProject)}&limit=50`,
  );
  expect(modelResponse.status()).toBe(200);
  const models = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(await modelResponse.json());
  expect(models.length).toBeGreaterThanOrEqual(8);
  await expect(page.locator("tbody tr")).toHaveCount(models.length);
  for (const model of models)
    await expect(
      page.locator(`a[href="/models/${encodeURIComponent(model.id)}"]`),
    ).toHaveText(model.name);
  const firstHref = await page
    .locator("tbody tr a")
    .first()
    .getAttribute("href");
  const firstModel = z
    .object({ spec: z.object({ display_name: z.string() }) })
    .parse(await (await page.request.get("/api/v1" + firstHref)).json());
  const firstName = firstModel.spec.display_name;
  await page.locator("tbody tr a").first().click();
  await expect(
    page.getByRole("heading", { name: firstName, exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: firstName, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "数据目录" })
    .click();
  const dataProject = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const dataResponse = await page.request.get(
    `/api/v1/data-assets/search?project_id=${encodeURIComponent(dataProject)}&limit=50`,
  );
  expect(dataResponse.status()).toBe(200);
  const dataItems = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(await dataResponse.json());
  expect(dataItems.length).toBeGreaterThanOrEqual(11);
  await expect(page.locator("tbody tr")).toHaveCount(dataItems.length);
  for (const item of dataItems)
    await expect(
      page.locator(`a[href="/data/${encodeURIComponent(item.id)}"]`),
    ).toHaveText(item.name);

  await page
    .getByRole("navigation")
    .getByRole("link", { name: "场景空间" })
    .click();
  const sceneProject = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const sceneResponse = await page.request.get(
    `/api/v1/scenes?project_id=${encodeURIComponent(sceneProject)}&limit=50`,
  );
  expect(sceneResponse.status()).toBe(200);
  const scenes = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(await sceneResponse.json());
  expect(scenes.map((item) => item.name)).toEqual(
    expect.arrayContaining([
      "Synthetic coastal inundation screening",
      "Synthetic assessment scenario B",
      "Synthetic assessment scenario C",
    ]),
  );
  await expect(page.locator("tbody tr")).toHaveCount(scenes.length);
  for (const scene of scenes)
    await expect(
      page.locator(`a[href="/scenes/${encodeURIComponent(scene.id)}"]`),
    ).toHaveText(scene.name);
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "工作流", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "工作流", exact: true }),
  ).toBeVisible();
  const projectId = await page
    .getByRole("combobox", { name: "当前项目" })
    .inputValue();
  const response = await page.request.get(
    "/api/v1/workflows?project_id=" +
      encodeURIComponent(projectId) +
      "&limit=50",
  );
  expect(response.status()).toBe(200);
  const workflows = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(await response.json());
  expect(workflows.map((item) => item.name)).toEqual(
    expect.arrayContaining([
      "coastal_impact",
      "sustainability",
      "temporal_change",
    ]),
  );
  await expect(page.locator("tbody tr")).toHaveCount(workflows.length);
  for (const workflow of workflows)
    await expect(
      page
        .locator("tbody a")
        .filter({ hasText: workflow.name })
        .and(
          page.locator(
            `[href="/workflows/${encodeURIComponent(workflow.id)}"]`,
          ),
        ),
    ).toBeVisible();
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(
    page.getByRole("heading", { name: "登录工作空间" }),
  ).toBeVisible();
  expect((await page.request.get("/api/v1/projects")).status()).toBe(401);
  expect(browserErrors).toEqual([]);
});
