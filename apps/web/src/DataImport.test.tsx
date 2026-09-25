import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DataImport from "./DataImport";
vi.mock("./workspace", () => ({
  useWorkspace: () => ({ projectId: "project-one" }),
}));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("imports source bytes with declarations without requiring science JSON or reading whole file in memory", async () => {
  let sent: FormData | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      if (options.method === "POST") sent = options.body;
      return new Response(
        JSON.stringify({
          error_code: "DATA_FORMAT",
          message: "Test server rejects corrupt TIFF",
        }),
        { status: 422 },
      );
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <DataImport />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText("原始影像文件"), {
    target: { files: [new File(["real source bytes"], "source.tif")] },
  });
  fireEvent.change(screen.getByLabelText("数据名称"), {
    target: { value: "真实业务" },
  });
  fireEvent.change(screen.getByLabelText("数据来源"), {
    target: { value: "公开产品" },
  });
  fireEvent.change(screen.getByLabelText("使用许可"), {
    target: { value: "非商业" },
  });
  fireEvent.click(screen.getByRole("button", { name: "导入为数据资产" }));
  await screen.findByRole("alert");
  expect(sent?.get("project_id")).toBe("project-one");
  expect(JSON.parse(String(sent?.get("declaration")))).toEqual({
    name: "真实业务",
    source: "公开产品",
    license: "非商业",
    year: null,
  });
  expect(sent?.get("file")).toBeInstanceOf(File);
  expect(screen.queryByLabelText("变量JSON")).toBeNull();
});
