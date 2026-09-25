import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ResearchEditor } from "./ResearchEditor";
import { taskSchema } from "./draft";
import { researchSteps } from "./ResearchPanels";
import * as network from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
test("eight step controls are separate components; browsing does not mount whole task page or execute", async () => {
  const source = network.assetSchema.parse({
    id: "a",
    project_id: "p",
    revision: 1,
    name: "原名SHA缺口.tif",
    sha256: "x",
    size: 100,
    facts: {
      profile: "geotiff",
      standard_version: null,
      issues: [],
      layers: [
        {
          name: "raster",
          row_count: 4,
          preview: [],
          fields: [
            { name: "band_1", unit: null, concept: null, data_type: "float32" },
            { name: "band_2", unit: null, concept: null, data_type: "float32" },
          ],
        },
      ],
    },
  });
  const task = taskSchema.parse({
    id: "t",
    project_id: "p",
    revision: 1,
    updated: 1,
    draft: {
      title: "保留研究名",
      purpose: "assessment",
      selection: [{ asset_id: "a", revision: 1 }],
      mapping: [
        {
          asset_id: "a",
          field: "raster/band_1",
          unit: null,
          concept: null,
          support: null,
          template_id: null,
          role: "feature",
        },
      ],
      options: {},
    },
  });
  const api = vi
    .spyOn(network, "api")
    .mockImplementation((path) =>
      Promise.resolve(path.endsWith("/indicators") ? {task_id:"t",revision:1,items:[],selected:[]} : path.endsWith("/assets") ? [source] : []),
    );
  const run = vi.fn(),
    execute = vi.fn();
  function Surface() {
    const [step, setStep] =
      useState<(typeof researchSteps)[number]["id"]>("sources");
    return (
      <>
        <nav>
          {researchSteps.map((s) => (
            <button key={s.id} onClick={() => setStep(s.id)}>
              {s.title}
            </button>
          ))}
        </nav>
        <ResearchEditor
          initial={task}
          canEdit
          step={step}
          onController={vi.fn()}
          onDraftSummary={vi.fn()}
          onRun={run}
          onExecute={execute}
        />
      </>
    );
  }
  const router = createMemoryRouter([{ path: "/", element: <Surface /> }]);
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(api).toHaveBeenCalled());
  for (const step of researchSteps) {
    fireEvent.click(screen.getByRole("button", { name: step.title }));
    expect(screen.queryByRole("heading", { name: "综合评价" })).toBeNull();
    expect(screen.queryByLabelText("任务名称")).toBeNull();
    expect(screen.queryByRole("link", { name: "返回任务" })).toBeNull();
    expect(
      screen.queryByRole("button", { name: "生成对齐数据" }) !== null,
    ).toBe(step.id === "spatial");
    expect(
      screen.queryByRole("region", { name: "指标选择器" }) !== null,
    ).toBe(step.id === "indicators");
    expect(
      screen.queryByRole("button", { name: "运行综合计算" }) !== null,
    ).toBe(step.id === "synthesis");
  }
  expect(run).not.toHaveBeenCalled();
  expect(execute).not.toHaveBeenCalled();
  expect(
    api.mock.calls.every((c) => !c[2]?.method || c[2]?.method === "GET"),
  ).toBe(true);
});
