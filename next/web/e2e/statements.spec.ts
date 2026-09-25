import { evidenceDirectory, evidencePath } from "./evidence";
import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";

test("one scoped source statement survives reload and follows reused bytes without refilling", async ({
  page,
}) => {
  test.setTimeout(90000);
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access file required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByLabel("任务名称", { exact: true }).fill("来源集中声明测试");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  const name = "statement-" + Date.now() + ".csv";
  await page.getByLabel("添加资料", { exact: true }).setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from("id,statement_probe\n01," + Date.now() + "\n"),
  });
  await expect(
    page
      .getByRole("navigation", { name: "任务资料列表" })
      .getByRole("button", { name: name, exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("添加资料", { exact: true })).toBeEnabled();
  await page.getByText("集中补充或修订声明", { exact: true }).click();
  await page
    .getByLabel("资料来源说明", { exact: true })
    .fill("独立工程测试文件");
  await page
    .getByLabel("使用许可或限制", { exact: true })
    .fill("仅用于自动化验收");
  await page.getByLabel("已知观测年份", { exact: true }).fill("2022");
  await page
    .getByLabel("声明依据", { exact: true })
    .fill("技术测试声明，不用于海岸区正式结论");
  await expect(
    page.getByRole("status").filter({ hasText: "已保存到服务器" }),
  ).toBeVisible();
  await page.reload();
  await page.getByText("集中补充或修订声明", { exact: true }).click();
  await expect(page.getByLabel("已知观测年份", { exact: true })).toHaveValue(
    "2022",
  );
  const publish = page.waitForResponse(
    (r) =>
      r.url().endsWith("/publish-statement") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存并认可本批声明" }).click();
  const response = await publish;
  expect(response.status()).toBe(201);
  const first = (await response.json()).task;
  await expect(
    page.getByText("1 份资料已沿用有效声明", { exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "任务目录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "科研任务", exact: true }),
  ).toBeVisible();
  await page.getByLabel("任务名称", { exact: true }).fill("复用已认可来源");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page.getByLabel("添加资料", { exact: true })).toBeVisible();
  await page.getByText("复用数据资源中的文件", { exact: true }).click();
  await page.getByRole("button", { name: `使用 ${name}`, exact: true }).click();
  await expect(
    page.getByText("1 份资料已沿用有效声明", { exact: true }),
  ).toBeVisible();
  await page.getByText("1 份资料已沿用有效声明", { exact: true }).click();
  await expect(page.getByText("声明年份：2022", { exact: true })).toBeVisible();
  const current = await page.request.get(
    "/api/tasks/" + page.url().split("/").at(-1),
  );
  const task = await current.json();
  const asset = await page.request.get(
    "/api/assets/" + task.draft.selection[0].asset_id,
  );
  expect((await asset.json()).facts.observed_period).toBeNull();
  expect(task.draft.options.inherited_declarations).toEqual(
    first.draft.options.inherited_declarations,
  );
  await mkdir(evidenceDirectory, { recursive: true });
  await writeFile(
    evidencePath("source-statement.json"),
    JSON.stringify(
      {
        status: "PASS",
        task_url: page.url(),
        declared_year: 2022,
        file_observed_period: null,
        first_statement_fills: 4,
        second_task_statement_fills: 0,
        second_task_approvals: 0,
        scope: "same actual file hash only",
      },
      null,
      2,
    ),
  );
});
