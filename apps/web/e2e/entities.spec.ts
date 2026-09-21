import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("geographic entities persist revisions and render actual geometry", async ({
  page,
}) => {
  const credentials = z
    .object({ email: z.string(), password: z.string() })
    .parse(
      JSON.parse(await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8")),
    );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "地理实体", exact: true })
    .click();
  const name = `浏览器合成管理单元 ${Date.now()}`;
  await page.getByLabel("实体名称", { exact: true }).fill(name);
  await page.getByLabel("管理单元标识", { exact: true }).fill("browser-U1");
  await page
    .getByLabel("生效时间", { exact: true })
    .fill("2020-01-01T00:00:00Z");
  await page.getByLabel("几何文件", { exact: true }).setInputFiles({
    name: "synthetic.geojson",
    mimeType: "application/geo+json",
    buffer: Buffer.from(
      JSON.stringify({
        type: "Feature",
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [117, 31],
              [117.01, 31],
              [117.01, 31.01],
              [117, 31],
            ],
          ],
        },
        properties: { source: "synthetic browser acceptance" },
      }),
    ),
  });
  const create = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/entities") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存实体版本", exact: true }).click();
  const response = await create;
  expect(response.status()).toBe(201);
  const created = z
    .object({ spec: z.object({ id: z.string() }) })
    .parse(await response.json());
  await expect(
    page.getByRole("button", { name: `${name} · v1`, exact: true }),
  ).toBeVisible();
  await expect(
    page.getByLabel("地理实体地图", { exact: true }),
  ).toHaveAttribute("data-loaded", "true");
  await page.getByLabel("实体名称", { exact: true }).fill(name + " 修订");
  await page.getByRole("button", { name: "保存实体版本", exact: true }).click();
  await expect(
    page.getByRole("button", { name: `${name} 修订 · v2`, exact: true }),
  ).toBeVisible();
  await page.getByLabel("读取版本", { exact: true }).fill("1");
  await expect(page.getByLabel("实体名称", { exact: true })).toHaveValue(name);
  const stored = await page.request.get(
    `/api/v1/entities/${created.spec.id}?version=1`,
  );
  expect(stored.status()).toBe(200);
  expect((await stored.json()).spec.properties.source).toBe(
    "synthetic browser acceptance",
  );
  await page.getByRole("button", { name: "保存实体版本", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("VERSION_CONFLICT");
  await page.reload();
  await expect(
    page.getByRole("button", { name: `${name} 修订 · v2`, exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "../../artifacts/screenshots/geographic-entities.png",
    fullPage: true,
  });
});
