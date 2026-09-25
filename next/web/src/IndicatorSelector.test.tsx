import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { IndicatorSelector } from "./IndicatorSelector";
import * as network from "./api";
import type { TaskRecord } from "./draft";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});
const task: TaskRecord = {
  id: "t",
  project_id: "p",
  revision: 1,
  updated: 0,
  draft: {
    title: "工程研究",
    purpose: "assessment",
    selection: [],
    mapping: [],
    method_id: null,
    options: {},
  },
};
const row = {
  indicator_id: "indicator.ndvi",
  name: "NDVI",
  category: "生态环境",
  description: "植被指数",
  status: "missing",
  message: "还需要近红外波段",
  missing: ["近红外波段"],
  suggested_key: null,
  candidates: [],
  installation_status: "published",
  business_parameters: [],
};
test("ordinary selector shows needed data only and submits indicator intent without contracts", async () => {
  const saved = { ...task, revision: 2 };
  const replace = vi.fn();
  const request = vi
    .spyOn(network, "api")
    .mockImplementation(async (_path, _schema, options) =>
      options?.method === "POST"
        ? { task: saved, items: [] }
        : {
            task_id: "t",
            revision: 1,
            items: [
              row,
              {
                ...row,
                indicator_id: "indicator.npp",
                name: "NPP",
                installation_status: "not_installed",
              },
            ],
            selected: [],
          },
    );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <IndicatorSelector
        task={task}
        save={async () => task}
        replace={replace}
        onRun={vi.fn()}
        onAddData={vi.fn()}
      />
    </QueryClientProvider>,
  );
  await screen.findByText("还需要近红外波段");
  for (const label of [
    "科学含义",
    "单位",
    "算法入口",
    "空间尺度",
    "参数Schema",
  ]) {
    expect(screen.queryByLabelText(label)).toBeNull();
  }
  expect(screen.queryByText("NPP")).toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "添加" }));
  await waitFor(() => expect(replace).toHaveBeenCalledWith(saved));
  const writes = request.mock.calls.filter((c) => c[2]?.method === "POST");
  expect(writes).toHaveLength(1);
  expect(JSON.parse(writes[0]![2]!.body as string).items).toEqual([
    { indicator_id: "indicator.ndvi", parameters: {} },
  ]);
});

test("filter and favorite change neither input bindings nor execution", async () => {
  const request = vi
    .spyOn(network, "api")
    .mockResolvedValue({
      task_id: "t",
      revision: 1,
      items: [row],
      selected: [],
    });
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <IndicatorSelector
        task={task}
        save={async () => task}
        replace={vi.fn()}
        onRun={vi.fn()}
        onAddData={vi.fn()}
      />
    </QueryClientProvider>,
  );
  await screen.findByText("NDVI");
  fireEvent.click(screen.getByRole("button", { name: "常用 NDVI" }));
  fireEvent.change(screen.getByLabelText("搜索指标"), {
    target: { value: "城市" },
  });
  expect(request.mock.calls.every((c) => !c[2]?.method)).toBe(true);
});
