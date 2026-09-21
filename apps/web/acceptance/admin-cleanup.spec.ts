import { mkdir, readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("administrator archives old demos reversibly and leaves only three real scenes in the workspace", async ({
  page,
}) => {
  const access = z
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
  const real = JSON.parse(
    await readFile(
      new URL(
        "../../../artifacts/runtime/real-imagery/demo-report.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("link", { name: "系统管理", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "账号管理", exact: true }),
  ).toBeVisible();
  const historical = [
    {
      id: "9d6a97f4-edf9-59c7-8356-47aa9b2e0eca",
      name: "CoastMAS synthetic demonstrations",
    },
    {
      id: "9bdf974b-5ad4-5245-a8cd-c9420690f64b",
      name: "待归档：首轮真实影像（校准冲突，不可用于分析）",
    },
  ];
  for (const item of historical) {
    const before = await (
      await page.request.get(`/api/v1/dashboard?project_id=${item.id}`)
    ).json();
    const hide = page.getByRole("button", {
      name: `归档项目 ${item.name}`,
      exact: true,
    });
    if (await hide.count()) await hide.click();
    const restore = page.getByRole("button", {
      name: `恢复项目 ${item.name}`,
      exact: true,
    });
    await expect(restore).toBeVisible();
    await restore.click();
    await expect(hide).toBeVisible();
    await hide.click();
    await expect(restore).toBeVisible();
    const after = await (
      await page.request.get(`/api/v1/dashboard?project_id=${item.id}`)
    ).json();
    expect(after.counts).toEqual(before.counts);
  }
  await mkdir(new URL("../../../artifacts/screenshots/", import.meta.url), {
    recursive: true,
  });
  await page.screenshot({
    path: "../../artifacts/screenshots/admin-archive.png",
    fullPage: true,
  });
  const projects = await (await page.request.get("/api/v1/projects")).json();
  expect(projects.map((item: { id: string }) => item.id)).toEqual([
    real.project_id,
  ]);
  await page.getByRole("link", { name: "项目概览", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "当前项目", exact: true }),
  ).toHaveValue(real.project_id);
  await page.getByRole("link", { name: "场景空间", exact: true }).click();
  for (const name of [
    "黄河口真实影像植被指数",
    "胶州湾真实影像水体指数",
    "长江口真实影像双期植被变化",
  ])
    await expect(page.getByRole("link", { name, exact: true })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(3);
  await page.screenshot({
    path: "../../artifacts/screenshots/real-demo-catalog.png",
    fullPage: true,
  });
});
