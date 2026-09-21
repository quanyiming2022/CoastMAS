import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("research UI freezes inputs and real worker publishes honest A/B/C partial report", async ({
  page,
}) => {
  test.setTimeout(120000);
  const access = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8")),
    );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("link", { name: "科研评估", exact: true }).click();
  const project = await page
    .getByRole("combobox", { name: "当前项目", exact: true })
    .inputValue();
  const sceneRows = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(
      await (
        await page.request.get(`/api/v1/scenes?project_id=${project}`)
      ).json(),
    );
  const scene = sceneRows.find(
    (row) => row.name === "Synthetic assessment scenario B",
  )!;
  expect(scene).toBeTruthy();
  const workflows = z
    .array(z.object({ id: z.string(), name: z.string() }))
    .parse(
      await (
        await page.request.get(`/api/v1/workflows?project_id=${project}`)
      ).json(),
    );
  const workflow = workflows.find((row) => row.name === "sustainability")!;
  expect(workflow).toBeTruthy();
  const revision = await (
    await page.request.get(
      `/api/v1/workflows/${encodeURIComponent(workflow.id)}`,
    )
  ).json();
  const graph = z
    .object({
      nodes: z.array(z.object({ model_id: z.string() })),
      input_bindings: z.array(
        z.object({ source: z.object({ id: z.string() }) }),
      ),
    })
    .parse(revision.spec);
  await page
    .getByRole("combobox", { name: "研究场景", exact: true })
    .selectOption(scene.id);
  for (const id of new Set(graph.nodes.map((n) => n.model_id)))
    await page
      .getByRole("checkbox", { name: `选择模型 ${id}`, exact: true })
      .check();
  for (const id of new Set(graph.input_bindings.map((b) => b.source.id)))
    await page
      .getByRole("checkbox", { name: `选择数据 ${id}`, exact: true })
      .check();
  await page.getByRole("button", { name: "加入固定样例", exact: true }).click();
  const submitted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/v1/research") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "提交科研评估", exact: true }).click();
  const response = await submitted;
  expect(response.status()).toBe(202);
  const job = await response.json();
  await expect(page.getByText("部分完成", { exact: true })).toBeVisible({
    timeout: 60000,
  });
  await expect(
    page.getByRole("table", { name: "科研分组统计" }).locator("tbody tr"),
  ).toHaveCount(3);
  const download = page.waitForEvent("download");
  await page
    .getByRole("link", { name: "下载完整科研报告", exact: true })
    .click();
  const payload = JSON.parse(
    await readFile((await (await download).path())!, "utf8"),
  );
  expect(payload.provider_requests).toBe(0);
  expect(payload.report.status).toBe("PARTIAL");
  expect(
    payload.report.trials.map(
      (t: { observation: { status: string } }) => t.observation.status,
    ),
  ).toEqual(["EVALUATED", "BLOCKED", "BLOCKED"]);
  expect(payload.report.trials[0].observation.workflow_valid).toBe(true);
  expect(
    payload.report.metrics.every(
      (m: { manual_correction_count: unknown }) =>
        m.manual_correction_count === null,
    ),
  ).toBe(true);
  expect(payload.research_manifest.cases[0].scene).toMatchObject({
    id: scene.id,
    version: 1,
  });
  await page.screenshot({
    path: "../../artifacts/screenshots/research-evaluation.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "结果中心", exact: true }).click();
  await page.locator(`a[href="/research/${job.id}"]`).click();
  await expect(page.getByText("部分完成", { exact: true })).toBeVisible();
});
