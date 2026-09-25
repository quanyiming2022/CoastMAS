import { test, expect } from "@playwright/test";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { evidenceDirectory, evidencePath } from "./evidence";

test("source grant and revocation show server-confirmed state in a new isolated project", async ({
  page,
}) => {
  if (!process.env.COASTMAS_NEXT_ACCESS_FILE)
    throw new Error("Explicit isolated access required");
  const access = JSON.parse(
    await readFile(process.env.COASTMAS_NEXT_ACCESS_FILE, "utf8"),
  );
  await page.goto("/?project=" + access.project_id);
  await page.getByLabel("邮箱", { exact: true }).fill(access.email);
  await page.getByLabel("密码", { exact: true }).fill(access.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await page.getByRole("link", { name: "系统管理", exact: true }).click();
  await page
    .getByLabel("新项目名称", { exact: true })
    .fill("来源授权隔离验证 " + Date.now());
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/projects") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "建立项目", exact: true }).click();
  const project = (await (await created).json()).id;
  await expect(page).toHaveURL(new RegExp("project=" + project + "$"));
  const section = page
    .getByRole("heading", { name: "本地来源授权", exact: true })
    .locator("..");
  const grant = section
    .getByRole("button", { name: /^授权 .* 的项目接入$/ })
    .first();
  await expect(grant).toBeEnabled();
  const grantResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/grant") &&
      response.request().method() === "POST",
  );
  await grant.click();
  expect((await (await grantResponse).json()).granted).toBe(true);
  const revoke = section
    .getByRole("button", { name: /^撤销 .* 的项目接入$/ })
    .first();
  await expect(revoke).toBeEnabled();
  const revokeResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/grant") &&
      response.request().method() === "DELETE",
  );
  await revoke.click();
  expect((await (await revokeResponse).json()).granted).toBe(false);
  await expect(grant).toBeEnabled();
  await page.reload();
  await expect(grant).toBeEnabled();
  const actual = await (
    await page.request.get(`/api/projects/${project}/local-sources`)
  ).json();
  expect(actual[0].granted).toBe(false);
  await mkdir(evidenceDirectory, { recursive: true });
  for (const [width, height] of [
    [1440, 900],
    [390, 844],
  ]) {
    await page.setViewportSize({ width, height });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width + 1);
    await section.screenshot({
      path: evidencePath(`source-authorization-${width}.png`),
    });
  }
  await writeFile(
    evidencePath("source-authorization.json"),
    JSON.stringify(
      {
        project_id: project,
        grant_verified: true,
        revoke_verified: true,
        refresh_verified: true,
        source_files_modified: false,
      },
      null,
      2,
    ),
  );
});
