import { readFile } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { z } from "zod";

test("static model decomposition preserves code, explicit dependencies and atomic black boxes", async ({
  page,
}) => {
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
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(credentials.email);
  await page.getByLabel("密码", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "项目概览", exact: true }),
  ).toBeVisible();
  await page.goto("/models/decompose");
  await page
    .getByRole("textbox", { name: "待拆解模型名称", exact: true })
    .fill("Static model");
  await page
    .getByRole("textbox", { name: "待分析的 Python 源码", exact: true })
    .fill(
      'raise RuntimeError("must never execute")\ndef preprocess(x): return x\ndef compute(x): return preprocess(x) * 2\ndef postprocess(x): return compute(x) + 1',
    );
  async function generate() {
    const response = page.waitForResponse(
      (r) =>
        r.url().endsWith("/models/decompose") &&
        r.request().method() === "POST",
    );
    await page
      .getByRole("button", { name: "生成拆解候选", exact: true })
      .click();
    const received = await response;
    expect(received.status()).toBe(200);
    const result = await received.json();
    expect(result.review_required).toBe(true);
    expect(result.executable).toBe(false);
    await expect(
      page.getByRole("heading", { name: "待审核拆解候选", exact: true }),
    ).toBeVisible();
    return result;
  }
  const python = await generate();
  expect(python.dependencies).toEqual([
    ["compute", "postprocess"],
    ["preprocess", "compute"],
  ]);
  await expect(page.locator(".react-flow__node")).toHaveCount(3);
  await expect(
    page.getByText("top-level statements are not executed", { exact: true }),
  ).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载拆解候选", exact: true }).click();
  expect(
    JSON.parse(await readFile((await (await download).path())!, "utf8")),
  ).toEqual(python);
  await page.screenshot({
    path: "../../artifacts/screenshots/model-decomposer.png",
    fullPage: true,
  });
  await page
    .getByRole("textbox", { name: "待拆解模型名称", exact: true })
    .fill("Changed model");
  await expect(
    page.getByRole("button", { name: "下载拆解候选", exact: true }),
  ).toHaveCount(0);
  const mode = page.getByRole("combobox", { name: "拆解方式", exact: true });
  await mode.selectOption("black_box");
  const blackBox = await generate();
  expect(blackBox.components).toHaveLength(1);
  expect(blackBox.components[0].atomic).toBe(true);
  expect(blackBox.dependencies).toEqual([]);
  await mode.selectOption("cli");
  await page
    .getByRole("textbox", { name: "完整命令行参数", exact: false })
    .fill("tool\n--increment=0\n--input\npath with spaces.tif");
  const cli = await generate();
  expect(cli.cli_arguments.increment).toBe("0");
  expect(cli.cli_arguments.input).toBe("path with spaces.tif");
  await mode.selectOption("pipeline");
  await page.getByLabel("上传组件与依赖 JSON", { exact: true }).setInputFiles({
    name: "pipeline.json",
    mimeType: "application/json",
    buffer: Buffer.from(
      JSON.stringify({
        name: "Unselected name",
        kind: "black_box",
        components: [
          { id: "prepare", stage: "preprocess" },
          { id: "run", stage: "compute" },
        ],
        dependencies: [["prepare", "run"]],
      }),
    ),
  });
  await expect(
    page.getByText("已读取：pipeline.json", { exact: true }),
  ).toBeVisible();
  const pipeline = await generate();
  expect(pipeline.model_name).toBe("Changed model");
  expect(pipeline.mode).toBe("WHITE_BOX");
  expect(pipeline.dependencies).toEqual([["prepare", "run"]]);
  expect(errors).toEqual([]);
});
