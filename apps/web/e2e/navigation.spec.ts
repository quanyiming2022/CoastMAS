import { mkdir, readFile, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";

const phase = process.env.COASTMAS_NAV_PHASE ?? "after";
const root = `../../artifacts/navigation/${phase}`;
const viewports = [
  { width: 1440, height: 900 },
  { width: 1366, height: 768 },
  { width: 390, height: 844 },
];
test("navigation visual baseline and authorized pages", async ({ page }) => {
  await mkdir(root, { recursive: true });
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  for (const path of ["/dashboard", "/admin"]) {
    await page.goto(path);
    await expect(
      page.getByRole("heading", {
        name: path === "/admin" ? "系统管理" : "项目概览",
        exact: true,
      }),
    ).toBeVisible();
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      if (phase === "after" && viewport.width === 390)
        await page.getByRole("button", { name: "打开导航" }).click();
      await page.screenshot({
        path: `${root}/${path.slice(1)}-${viewport.width}.png`,
      });
      if (phase === "after" && viewport.width === 390)
        await page.keyboard.press("Escape");
    }
  }
});

const expectedPaths = [
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
];
const groupNames = ["场景与数据", "模型与编排", "运行与成果", "评价与协同"];
async function expandAll(page: Page) {
  for (const name of groupNames) {
    const group = page.getByRole("button", { name, exact: true });
    if ((await group.getAttribute("aria-expanded")) === "false")
      await group.click();
  }
}
async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  const response = page.waitForResponse(
    (r) => r.url().endsWith("/auth/login") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "登录", exact: true }).click();
  const csrf = (await (await response).json()).csrf_token as string;
  await expect(page.getByRole("combobox", { name: "当前项目" })).toBeVisible();
  return csrf;
}
test("NAV-01 real route, state, permissions and drawer regression", async ({
  page,
  browser,
}) => {
  if (phase === "before") return; // Before implementation the flat menu has no grouping or drawer.
  test.setTimeout(180000);
  const credentials = JSON.parse(
    await readFile(process.env.COASTMAS_E2E_ACCESS_FILE!, "utf8"),
  );
  const csrf = await login(page, credentials.email, credentials.password);
  const headers = { "X-CSRF-Token": csrf };
  const project = await page
    .getByRole("combobox", { name: "当前项目" })
    .inputValue();
  await expandAll(page);
  expect(
    await page
      .locator(".sidebar .nav-item")
      .evaluateAll((links) => links.map((link) => link.getAttribute("href"))),
  ).toEqual(expectedPaths);
  const coverage: unknown[] = [];
  for (const path of expectedPaths) {
    await expandAll(page);
    await page.locator(`.sidebar .nav-item[href="${path}"]`).click();
    await expect(page).toHaveURL(new RegExp(path + "$"));
    await expect(page.locator("main h1").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "页面不存在", exact: true }),
    ).toHaveCount(0);
    await expect(page.locator('.sidebar [aria-current="page"]')).toHaveCount(1);
    await expect(
      page.locator('.sidebar [aria-current="page"]'),
    ).toHaveAttribute("href", path);
    coverage.push({
      path,
      heading: await page.locator("main h1").first().textContent(),
    });
  }
  await page.goto("/models");
  const models = await (
    await page.request.get(`/api/v1/models?project_id=${project}`)
  ).json();
  const detail = `/models/${models[0].id}/edit?version=1#inputs`;
  await page.goto(detail);
  await expect(page.locator('.sidebar [aria-current="page"]')).toHaveAttribute(
    "href",
    "/models",
  );
  await page.getByRole("button", { name: "模型与编排", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "模型与编排", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(
    page.getByRole("button", { name: "模型与编排", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("link", { name: "数据目录", exact: true }).click();
  await page.goBack();
  expect(
    new URL(page.url()).pathname +
      new URL(page.url()).search +
      new URL(page.url()).hash,
  ).toBe(detail);
  await expect(page.locator('.sidebar [aria-current="page"]')).toHaveAttribute(
    "href",
    "/models",
  );
  await page.goForward();
  await expect(page.locator('.sidebar [aria-current="page"]')).toHaveAttribute(
    "href",
    "/data",
  );
  // Non-current group preferences survive refresh; current group is opened on entry.
  await page.getByRole("button", { name: "模型与编排", exact: true }).click();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "模型与编排", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  const created = await page.request.post("/api/v1/projects", {
    headers,
    data: { name: "NAV isolated project" },
  });
  expect(created.status()).toBe(201);
  const second = (await created.json()).id;
  await page.reload();
  await page.getByRole("combobox", { name: "当前项目" }).selectOption(second);
  await page.getByRole("link", { name: "时间适配", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "当前项目" })).toHaveValue(
    second,
  );
  await page.getByLabel("名称", { exact: true }).fill("导航开合不得清空此草稿");
  await page.getByRole("button", { name: "场景与数据", exact: true }).click();
  await expect(page.getByLabel("名称", { exact: true })).toHaveValue(
    "导航开合不得清空此草稿",
  );
  await page.getByRole("button", { name: "场景与数据", exact: true }).click();
  await expect(page.getByLabel("名称", { exact: true })).toHaveValue(
    "导航开合不得清空此草稿",
  );
  await page.getByRole("combobox", { name: "当前项目" }).selectOption(project);
  const scenes = await (
    await page.request.get(`/api/v1/scenes?project_id=${project}`)
  ).json();
  await page.goto(`/scenes/${scenes[0].id}/workspace`);
  const map = page.locator(".geographic-map canvas").first();
  await expect(map).toBeVisible();
  const originalMap = await map.elementHandle();
  await page.getByRole("button", { name: "场景与数据", exact: true }).click();
  expect(
    await map.evaluate((node, original) => node === original, originalMap),
  ).toBe(true);
  const workflows = await (
    await page.request.get(`/api/v1/workflows?project_id=${project}`)
  ).json();
  await page.goto(`/workflows/${workflows[0].id}`);
  const graph = page.locator(".react-flow").first();
  await expect(graph).toBeVisible();
  const originalGraph = await graph.elementHandle();
  await page.getByRole("button", { name: "模型与编排", exact: true }).click();
  expect(
    await graph.evaluate((node, original) => node === original, originalGraph),
  ).toBe(true);
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    if (viewport.width === 390)
      await page.getByRole("button", { name: "打开导航" }).click();
    await expandAll(page);
    await page.screenshot({ path: `${root}/expanded-${viewport.width}.png` });
    const layout = await page.locator(".sidebar").evaluate((el) => {
      const footer = el.querySelector(".sidebar-foot")!.getBoundingClientRect();
      const brand = el.querySelector(".sidebar-brand")!.getBoundingClientRect();
      const nav = el.querySelector("nav")!;
      return {
        footerBottom: footer.bottom,
        brandTop: brand.top,
        navHeight: nav.clientHeight,
        width: innerWidth,
        scroll: document.documentElement.scrollWidth,
        height: innerHeight,
      };
    });
    expect(layout.footerBottom).toBeLessThanOrEqual(viewport.height);
    expect(layout.brandTop).toBeGreaterThanOrEqual(0);
    expect(layout.navHeight).toBeGreaterThan(0);
    expect(layout.scroll).toBeLessThanOrEqual(viewport.width + 1);
    for (const name of groupNames)
      await page.getByRole("button", { name, exact: true }).click();
    await page.screenshot({ path: `${root}/collapsed-${viewport.width}.png` });
    if (viewport.width === 390) {
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).not.toBeVisible();
      await expect(
        page.getByRole("button", { name: "打开导航" }),
      ).toBeFocused();
      await page.getByRole("button", { name: "打开导航" }).click();
      const close = page.getByRole("button", { name: "关闭导航" });
      await close.focus();
      await page.keyboard.press("Shift+Tab");
      expect(
        await page.evaluate(() => !!document.activeElement?.closest("dialog")),
      ).toBe(true);
      await page.getByRole("link", { name: "科研验证", exact: true }).click();
      await expect(page.getByRole("dialog")).not.toBeVisible();
    }
  }
  await page.setViewportSize({ width: 1366, height: 360 });
  await expandAll(page);
  await expect(page.getByRole("button", { name: "退出登录" })).toBeInViewport();
  await expect(page.locator(".sidebar-brand")).toBeInViewport();
  await page.screenshot({ path: `${root}/short-window.png` });
  const email =
    "ordinary-" + randomUUID().replaceAll("-", "") + "@navigation-test.invalid";
  const password = randomUUID() + randomUUID();
  const user = await page.request.post("/api/v1/admin/users", {
    headers,
    data: { email, password },
  });
  expect(user.status()).toBe(201);
  expect(
    (
      await page.request.put(
        `/api/v1/projects/${project}/members/${(await user.json()).id}`,
        { headers, data: { role: "VIEWER" } },
      )
    ).status(),
  ).toBe(200);
  const context = await browser.newContext({ viewport: viewports[0] });
  const ordinary = await context.newPage();
  await login(ordinary, email, password);
  await expandAll(ordinary);
  await expect(
    ordinary.getByRole("link", { name: "系统管理", exact: true }),
  ).toHaveCount(0);
  expect((await ordinary.request.get("/api/v1/admin/users")).status()).toBe(
    403,
  );
  expect(await ordinary.locator(".sidebar .nav-item").count()).toBe(
    expectedPaths.length - 1,
  );
  for (const path of expectedPaths.filter((path) => path !== "/admin")) {
    await ordinary.locator(`.sidebar .nav-item[href="${path}"]`).click();
    await expect(ordinary.locator("main h1").first()).toBeVisible();
    await expect(
      ordinary.getByRole("heading", { name: "页面不存在", exact: true }),
    ).toHaveCount(0);
  }
  await ordinary.screenshot({ path: `${root}/ordinary-long-email.png` });
  await expect(ordinary.locator(".sidebar-account")).toHaveAttribute(
    "title",
    email,
  );
  await ordinary.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect(
    ordinary.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  await context.close();
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => {
      throw new Error("storage unavailable");
    };
    Storage.prototype.setItem = () => {
      throw new Error("storage unavailable");
    };
  });
  await page.setViewportSize(viewports[0]!);
  await page.goto("/models");
  await expect(
    page.getByRole("button", { name: "模型与编排", exact: true }),
  ).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("button", { name: "模型与编排", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "模型与编排", exact: true }),
  ).toHaveAttribute("aria-expanded", "false");
  await writeFile(
    `${root}/route-coverage.json`,
    JSON.stringify(coverage, null, 2),
  );
});
