import { mkdir, readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("three real image scenes, two acquisitions, immutable results and actual internet basemaps", async ({
  page,
}) => {
  test.setTimeout(180000);
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
  const report = z
    .object({
      project_id: z.string(),
      scenes: z.record(
        z.string(),
        z.object({
          scene_id: z.string(),
          workflow_id: z.string(),
          result_id: z.string(),
          status: z.literal("SUCCEEDED"),
        }),
      ),
    })
    .parse(
      JSON.parse(
        await readFile(
          new URL(
            "../../../artifacts/runtime/real-imagery/demo-report.json",
            import.meta.url,
          ),
          "utf8",
        ),
      ),
    );
  expect(Object.keys(report.scenes)).toHaveLength(3);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await mkdir(new URL("../../../artifacts/screenshots/", import.meta.url), {
    recursive: true,
  });
  for (const [key, scene] of Object.entries(report.scenes)) {
    const loadedImage = page.waitForResponse(
      (response) =>
        response.url().includes("/image?version=1") &&
        response.status() === 200,
    );
    await page.goto(
      "/scenes/" + encodeURIComponent(scene.scene_id) + "/workspace",
    );
    await page
      .getByLabel("当前项目", { exact: true })
      .selectOption(report.project_id);
    await loadedImage;
    await expect(
      page.getByLabel("显示真实影像", { exact: true }),
    ).toBeChecked();
    await expect(page.locator(".geographic-map")).toHaveAttribute(
      "data-loaded",
      "true",
    );
    await expect(
      page.getByText("Copernicus Sentinel-2 / Earth Search", { exact: false }),
    ).toBeVisible();
    if (key === "yangtze") {
      await expect(
        page
          .getByRole("combobox", { name: "影像与采集时间", exact: true })
          .locator("option"),
      ).toHaveCount(2);
      const earlier = page.waitForResponse(
        (response) =>
          response.url().includes("&frame=1") && response.status() === 200,
      );
      await page
        .getByRole("combobox", { name: "影像与采集时间", exact: true })
        .selectOption({ index: 1 });
      await earlier;
      await expect(page.locator(".geographic-map")).toHaveAttribute(
        "data-loaded",
        "true",
      );
    }
    if (key === "yellow-river") {
      const street = page.waitForResponse(
        (response) =>
          response.url().startsWith("https://tile.openstreetmap.org/") &&
          response.status() === 200,
      );
      await page
        .getByRole("combobox", { name: "地图底图", exact: true })
        .selectOption("osm");
      await street;
      await expect(
        page.getByRole("link", { name: "OpenStreetMap" }),
      ).toBeVisible();
      const nasa = page.waitForResponse(
        (response) =>
          response.url().startsWith("https://gibs.earthdata.nasa.gov/") &&
          response.status() === 200,
      );
      await page
        .getByRole("combobox", { name: "地图底图", exact: true })
        .selectOption("nasa");
      await nasa;
      await expect(
        page.getByText("NASA EOSDIS GIBS", { exact: false }),
      ).toBeVisible();
      await page
        .getByRole("combobox", { name: "地图底图", exact: true })
        .selectOption("none");
    }
    await page
      .locator(".geographic-map")
      .screenshot({
        path: `../../artifacts/screenshots/real-${key}-scene.png`,
      });
    await page.goto("/results/" + encodeURIComponent(scene.result_id));
    await page
      .getByLabel("当前项目", { exact: true })
      .selectOption(report.project_id);
    await expect(
      page.getByRole("heading", { name: "结果与科研追溯" }),
    ).toBeVisible();
    await expect(page.getByText("固定色标", { exact: false })).toBeVisible();
    await expect(page.locator(".geographic-map")).toHaveAttribute(
      "data-loaded",
      "true",
    );
    await expect(page.getByText("栅格矩阵：", { exact: false })).toBeVisible();
    await page
      .locator(".geographic-map")
      .screenshot({
        path: `../../artifacts/screenshots/real-${key}-result.png`,
      });
    const payload = await (
      await page.request.get(`/api/v1/results/${scene.result_id}/content`)
    ).json();
    expect(payload.llm_calls).toBe(0);
    expect(payload.outputs["optical.summary"].valid_pixels).toBeGreaterThan(0);
    expect(payload.run_manifest.scene.id).toBe(scene.scene_id);
  }
  expect(errors).toEqual([]);
});
