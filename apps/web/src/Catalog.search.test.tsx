import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceProvider } from "./workspace";
import Catalog from "./Catalog";
import { freshModel } from "./model-editor";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("searches the project model catalogue on the server rather than filtering a previously loaded page", async () => {
  const calls: string[] = [];
  const spec = {
    ...freshModel("owner", "2026-09-21T00:00:00Z"),
    id: "found",
    name: "Remote model",
    display_name: "Remote model",
    license: "MIT",
    spatial_scale: { unit: "m" },
    temporal_scale: { unit: "s" },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      calls.push(input);
      if (input.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            { id: "project", name: "Project", owner_id: "owner" },
          ]),
        );
      return new Response(
        JSON.stringify(
          input.includes("q=Remote")
            ? [
                {
                  id: "found",
                  name: spec.name,
                  version: 1,
                  enabled: true,
                  spec,
                },
              ]
            : [],
        ),
      );
    }),
  );
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <WorkspaceProvider>
          <Catalog kind="models" />
        </WorkspaceProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: "搜索全部模型" }),
    { target: { value: "Remote" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "搜索模型" }));
  await waitFor(() =>
    expect(
      calls.some(
        (url) => url.includes("/models/search?") && url.includes("q=Remote"),
      ),
    ).toBe(true),
  );
  expect(
    await screen.findByRole("link", { name: "Remote model" }),
  ).toHaveAttribute("href", "/models/found");
});

it("searches and filters data across server pages", async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) => {
      calls.push(input);
      if (input.endsWith("/projects"))
        return new Response(
          JSON.stringify([
            { id: "project", name: "Project", owner_id: "owner" },
          ]),
        );
      return new Response(
        JSON.stringify(
          input.includes("q=Remote")
            ? [
                {
                  id: "remote-data",
                  name: "Remote data",
                  version: 1,
                  enabled: true,
                  published: false,
                  summary: { type: "table", format: "CSV" },
                },
              ]
            : [],
        ),
      );
    }),
  );
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <WorkspaceProvider>
          <Catalog kind="data" />
        </WorkspaceProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  fireEvent.change(
    await screen.findByRole("textbox", { name: "搜索全部数据" }),
    { target: { value: "Remote" } },
  );
  fireEvent.change(screen.getByRole("combobox", { name: "文件格式筛选" }), {
    target: { value: "CSV" },
  });
  fireEvent.click(screen.getByRole("button", { name: "搜索数据" }));
  await waitFor(() =>
    expect(
      calls.some(
        (url) =>
          url.includes("/data-assets/search?") &&
          url.includes("q=Remote") &&
          url.includes("data_format=CSV"),
      ),
    ).toBe(true),
  );
  expect(
    await screen.findByRole("link", { name: "Remote data" }),
  ).toHaveAttribute("href", "/data/remote-data");
});
