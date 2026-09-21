import { mkdir, readFile, writeFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";

test("all existing business pages and editor families fit desktop and mobile", async ({
  page,
}) => {
  test.setTimeout(240000);
  const root = "../../artifacts/ui-consistency/coverage";
  await mkdir(root, { recursive: true });
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "当前项目" })).toBeVisible();
  const project = await page
    .getByRole("combobox", { name: "当前项目" })
    .inputValue();
  const routes = [
    "/dashboard",
    "/scenes",
    "/data",
    "/entities",
    "/temporal",
    "/planner",
    "/workflows",
    "/models",
    "/knowledge-graph",
    "/runs",
    "/results",
    "/assessments",
    "/optimizations",
    "/collaboration",
    "/research",
    "/admin",
    "/assessment-records",
    "/data-sources",
    "/models/decompose",
    "/scenes/new",
    "/data/new",
    "/models/new",
    "/workflows/new",
    "/assessments/new",
    "/optimizations/new",
    "/data-sources/new",
  ];
  const catalogs: Record<string, { id: string }[]> = {};
  for (const [endpoint, path, suffix] of [
    ["models", "models", "/edit"],
    ["scenes", "scenes", "/workspace"],
    ["data-assets", "data", "/workspace"],
    ["workflows", "workflows", "/edit"],
    ["jobs", "runs", ""],
    ["results", "results", ""],
  ]) {
    const response = await page.request.get(
      `/api/v1/${endpoint}?project_id=${project}`,
    );
    expect(response.status()).toBe(200);
    const rows = await response.json();
    catalogs[endpoint!] = rows;
    const first = rows.find(
      (row: { result_type?: string }) =>
        row.result_type !== "research_evaluation",
    );
    if (first) {
      routes.push(`/${path}/${first.id}`);
      if (suffix) routes.push(`/${path}/${first.id}${suffix}`);
    }
  }
  for (const [endpoint, route, idField] of [
    ["indicator-frameworks", "assessments", "id"],
    ["assessments", "assessment-records", "resource_id"],
    ["optimizations", "optimizations", "resource_id"],
    ["data-sources", "data-sources", "resource_id"],
  ]) {
    const response = await page.request.get(
      `/api/v1/${endpoint}?project_id=${project}`,
    );
    expect(response.status()).toBe(200);
    const records = await response.json();
    if (records.length)
      routes.push(
        `/${route}/${encodeURIComponent(records[0][idField!] as string)}`,
      );
  }
  const researchResults = await (
    await page.request.get(`/api/v1/results?project_id=${project}`)
  ).json();
  const researchResult = researchResults.find(
    (item: { result_type: string }) =>
      item.result_type === "research_evaluation",
  );
  if (researchResult) routes.push(`/research/${researchResult.job_id}`);
  const resultIds = catalogs.results!.map((item) => item.id);
  if (resultIds.length >= 2)
    routes.push(`/results/compare?left=${resultIds[0]}&right=${resultIds[1]}`);
  const report: unknown[] = [];
  for (const [index, path] of routes.entries()) {
    await page.goto(path);
    await expect(page.locator("main h1").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "页面不存在", exact: true }),
    ).toHaveCount(0);
    // Settle genuine API loading before measuring or capturing; no mocked catalogs.
    await expect(page.getByRole("status")).toHaveCount(0, { timeout: 15000 });
    for (const viewport of [
      { width: 1440, height: 900 },
      { width: 1366, height: 768 },
      { width: 390, height: 844 },
    ]) {
      await page.setViewportSize(viewport);
      // Map/chart ResizeObservers render on the next frame after viewport changes.
      await page.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
      await expect
        .poll(() => page.evaluate(() => document.documentElement.scrollWidth), {
          message: `${path} persistent page overflow at ${viewport.width}`,
        })
        .toBeLessThanOrEqual(viewport.width + 1);
      await page.evaluate(() => window.scrollTo(0, 0));
      const layout = await page.evaluate(() => {
        const buttons = [
          ...document.querySelectorAll<HTMLButtonElement>("main button"),
        ].filter(
          (el) =>
            !el.closest(".react-flow, .maplibregl-map") &&
            el.checkVisibility() &&
            !el.closest("details:not([open])") &&
            el.getClientRects().length,
        );
        // A scrollable palette clips offscreen rows. Compare only each button's painted region.
        function paintedRect(element: HTMLElement) {
          const rect = element.getBoundingClientRect();
          const visible = {
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          };
          for (
            let parent = element.parentElement;
            parent;
            parent = parent.parentElement
          ) {
            const css = getComputedStyle(parent),
              bounds = parent.getBoundingClientRect();
            if (css.overflowX !== "visible") {
              visible.left = Math.max(visible.left, bounds.left);
              visible.right = Math.min(visible.right, bounds.right);
            }
            if (css.overflowY !== "visible") {
              visible.top = Math.max(visible.top, bounds.top);
              visible.bottom = Math.min(visible.bottom, bounds.bottom);
            }
          }
          return visible;
        }
        const overlaps: string[] = [];
        for (let a = 0; a < buttons.length; a++)
          for (let b = a + 1; b < buttons.length; b++) {
            const x = paintedRect(buttons[a]!),
              y = paintedRect(buttons[b]!);
            if (
              Math.min(x.right, y.right) - Math.max(x.left, y.left) > 2 &&
              Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 2
            )
              overlaps.push(
                `${buttons[a]!.textContent} / ${buttons[b]!.textContent}`,
              );
          }
        const lowContrast = [
          ...document.querySelectorAll<HTMLElement>(
            "main a.button:not(.secondary)",
          ),
        ]
          .filter((el) => el.checkVisibility())
          .filter((el) => {
            const css = getComputedStyle(el);
            const luminance = (color: string) => {
              const values = (color.match(/[\d.]+/g) ?? [])
                .slice(0, 3)
                .map(Number)
                .map((value) => value / 255)
                .map((value) =>
                  value <= 0.04045
                    ? value / 12.92
                    : Math.pow((value + 0.055) / 1.055, 2.4),
                );
              return (
                values[0]! * 0.2126 + values[1]! * 0.7152 + values[2]! * 0.0722
              );
            };
            const foreground = luminance(css.color),
              background = luminance(css.backgroundColor);
            return (
              (Math.max(foreground, background) + 0.05) /
                (Math.min(foreground, background) + 0.05) <
              4.5
            );
          })
          .map((el) => el.textContent);
        return {
          lowContrast,
          width: innerWidth,
          scroll: document.documentElement.scrollWidth,
          overlaps,
          tables: document.querySelectorAll("main table").length,
          scopedTables: document.querySelectorAll(
            "main .table-scroll > .data-table",
          ).length,
          heading: document.querySelector("main h1")?.textContent,
        };
      });
      report.push({ path, ...viewport, ...layout });
      await writeFile(`${root}/coverage.json`, JSON.stringify(report, null, 2));
      await page.screenshot({
        path: `${root}/${String(index).padStart(2, "0")}-${viewport.width}.png`,
      });
      expect
        .soft(layout.scroll, `${path} page overflow at ${viewport.width}`)
        .toBeLessThanOrEqual(viewport.width + 1);
      expect
        .soft(
          layout.overlaps,
          `${path} overlapping buttons at ${viewport.width}`,
        )
        .toEqual([]);
      expect
        .soft(layout.lowContrast, `${path} unreadable primary link button`)
        .toEqual([]);
      expect
        .soft(layout.scopedTables, `${path} bypassed shared table`)
        .toBe(layout.tables);
    }
  }
});
