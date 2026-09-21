import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test.beforeEach(async ({ page }) => {
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
});

test("create a real draft with model drag, ports, explicit parameters and blocked scientific preflight", async ({
  page,
}) => {
  await page.goto("/workflows/new");
  const canvas = page.getByLabel("工作流编辑画布", { exact: true });
  const screening = page.getByRole("button", {
    name: "Sea-level terrain screening · v1",
    exact: true,
  });
  await screening.dragTo(canvas, { targetPosition: { x: 100, y: 100 } });
  await expect(page.locator(".editor-node")).toHaveCount(1);
  await expect(
    page.getByLabel("increment [m]（必填）", { exact: true }),
  ).toHaveValue("");
  await page
    .getByRole("combobox", { name: "输入数据 · dem [m]", exact: true })
    .selectOption({ label: "dem.tif · v1" });
  await page.getByLabel("发布输出 · inundation [1]", { exact: true }).check();
  await page
    .getByRole("button", {
      name: "Population and land-use overlay · v1",
      exact: true,
    })
    .click();
  await expect(page.locator(".editor-node")).toHaveCount(2);
  await page.getByRole("button", { name: "Fit View", exact: true }).click();
  // Fit View is queued by React Flow; wait for measured nodes to fit before
  // taking coordinates for a real pointer gesture.
  await expect
    .poll(() =>
      canvas.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        return [...element.querySelectorAll(".react-flow__node")].every(
          (node) => {
            const box = node.getBoundingClientRect();
            return (
              box.top >= Math.max(bounds.top, 0) &&
              box.bottom <= Math.min(bounds.bottom, innerHeight) &&
              box.left >= bounds.left &&
              box.right <= bounds.right
            );
          },
        );
      }),
    )
    .toBe(true);
  const source = page.locator('[data-handleid="out:inundation"]');
  const target = page.locator('[data-handleid="in:inundation"]');
  await expect
    .poll(() =>
      source.evaluate((element) => {
        const box = element.getBoundingClientRect();
        return (
          document.elementFromPoint(
            box.x + box.width / 2,
            box.y + box.height / 2,
          ) === element
        );
      }),
    )
    .toBe(true);
  const start = await source.boundingBox();
  const end = await target.boundingBox();
  expect(start).not.toBeNull();
  expect(end).not.toBeNull();
  await page.mouse.move(
    start!.x + start!.width / 2,
    start!.y + start!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(end!.x + end!.width / 2, end!.y + end!.height / 2, {
    steps: 15,
  });
  await page.mouse.up();
  await expect(
    page.getByRole("button", { name: "删除连线 1", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "删除连线 1", exact: true }).click();
  await expect(page.locator(".react-flow__edge")).toHaveCount(0);
  await page.getByRole("button", { name: "删除选中节点", exact: true }).click();
  await expect(page.locator(".editor-node")).toHaveCount(1);
  await page
    .getByRole("combobox", { name: "选择节点", exact: true })
    .selectOption({ index: 1 });
  await page
    .getByRole("combobox", { name: "预检场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page.getByRole("button", { name: "校验当前草稿", exact: true }).click();
  await expect(page.getByText(/required parameter missing/)).toBeVisible();
  await page.getByLabel("increment [m]（必填）", { exact: true }).fill("0.5");
  const name = `浏览器合成草稿 ${Date.now()}`;
  await page.getByLabel("工作流名称", { exact: true }).fill(name);
  await expect(page.getByText(/PARAMETER_MISSING/)).toHaveCount(0);
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/workflows") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "保存工作流版本", exact: true })
    .click();
  const response = await created;
  expect(response.status()).toBe(201);
  const spec = (await response.json()).spec;
  expect(spec.nodes).toHaveLength(1);
  expect(spec.nodes[0].parameters).toEqual({ connectivity: 4, increment: 0.5 });
  expect(spec.input_bindings[0].source.version).toBe(1);
  expect(spec.output_definition[0].variable).toBe("inundation");
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
});

test("copy, revise and run a pinned workflow through actual worker and result storage", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/workflows");
  await page
    .getByRole("link", { name: "coastal_impact", exact: true })
    .first()
    .click();
  await page
    .getByRole("link", { name: "编辑工作流 / 另存副本", exact: true })
    .click();
  await expect(page.locator(".editor-node")).toHaveCount(3);
  const name = `浏览器工作流副本 ${Date.now()}`;
  await page.getByLabel("工作流名称", { exact: true }).fill(name);
  await page
    .getByRole("combobox", { name: "预检场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page.getByRole("button", { name: "校验当前草稿", exact: true }).click();
  await expect(page.getByText("已验证", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/workflow-editor.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "另存副本", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: name + " 副本", exact: true }),
  ).toBeVisible();
  const copiedId = decodeURIComponent(
    new URL(page.url()).pathname.split("/").at(-1)!,
  );
  await page
    .getByRole("link", { name: "编辑工作流 / 另存副本", exact: true })
    .click();
  await page.getByLabel("工作流名称", { exact: true }).fill(name + " 修订");
  await page
    .getByRole("button", { name: "保存工作流版本", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: name + " 修订", exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/版本 2 · 3 个计算节点/)).toBeVisible();
  const historical = await page.request.get(
    `/api/v1/workflows/${copiedId}?version=1`,
  );
  expect(historical.status()).toBe(200);
  expect((await historical.json()).spec.name).toBe(name + " 副本");
  await page
    .getByRole("combobox", { name: "运行场景", exact: true })
    .selectOption({ label: "Synthetic coastal inundation screening · v1" });
  await page.getByRole("button", { name: "科学预检", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "提交运行", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "提交运行", exact: true }).click();
  await page
    .getByRole("link", { name: "查看不可变结果" })
    .click({ timeout: 90000 });
  await expect(page.getByText("80000", { exact: true })).toBeVisible();
  await expect(page.getByText("320", { exact: true })).toBeVisible();
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "下载完整结果" }).click();
  const result = JSON.parse(
    await readFile((await (await downloadEvent).path())!, "utf8"),
  );
  expect(result.run_manifest.workflow.id).toBe(copiedId);
  expect(result.run_manifest.workflow.version).toBe(2);
  expect(result.llm_calls).toBe(0);
  expect(errors).toEqual([]);
});
