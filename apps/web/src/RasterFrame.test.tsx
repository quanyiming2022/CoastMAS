import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import RasterFrame from "./RasterFrame";
vi.mock("./workspace", () => ({ useWorkspace: () => ({ projectId: "p" }) }));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("prepares selected immutable versions using explicit units and sampling, without matrix input", async () => {
  let sent: unknown;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url, options) => {
      if (options.method === "POST") {
        sent = JSON.parse(options.body);
        return new Response(
          JSON.stringify({
            error_code: "CONSTRAINT_ERROR",
            message: "test rejection",
          }),
          { status: 422 },
        );
      }
      if (String(_url).includes("data%3Ax?version=3"))
        return new Response(
          JSON.stringify({
            resource_id: "data:x",
            version: 3,
            checksum: "a".repeat(64),
            spec: {
              id: "data:x",
              name: "real",
              version: 3,
              type: "raster",
              format: "GeoTIFF",
              uri: "s3://test/file",
              checksum: "a".repeat(64),
              crs: null,
              vertical_datum: null,
              spatial_extent: null,
              time_start: null,
              time_end: null,
              time_resolution: null,
              variables: [],
              quality: {
                declarations: {
                  value_unit: "m",
                  unit_evidence: "user_confirmation",
                },
              },
              source: "test",
              license: "test",
            },
          }),
        );
      return new Response(
        JSON.stringify([
          {
            id: "data:x",
            name: "real",
            version: 3,
            enabled: true,
            published: false,
            kind: "data",
            project_id: "p",
            summary: {},
          },
        ]),
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
        <RasterFrame />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "选择real" }));
  fireEvent.change(await screen.findByLabelText("变量名称"), {
    target: { value: "distance" },
  });
  expect((screen.getByLabelText("变量单位") as HTMLInputElement).value).toBe(
    "m",
  );
  fireEvent.change(screen.getByLabelText("输入资产名称"), {
    target: { value: "prepared" },
  });
  fireEvent.change(screen.getByRole("combobox", { name: "数据范围" }), {
    target: { value: "sample" },
  });
  fireEvent.change(screen.getByLabelText("样本数量上限"), {
    target: { value: "400" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "生成可用于模型的输入资产" }),
  );
  await screen.findByRole("alert");
  expect(sent).toEqual({
    project_id: "p",
    name: "prepared",
    features: [
      { asset_id: "data:x", version: 3, name: "distance", unit: "m", band: 1 },
    ],
    options: { mode: "sample", sample_size: 400, seed: 42, standardize: false },
  });
});
