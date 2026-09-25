import { afterEach, expect, test, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { researchSteps } from "./ResearchPanels";
import { LayerCatalog } from "./LayerCatalog";
import { ResearchContentManager } from "./ResearchContentManager";
import { ResearchStepPanel, stepStatus } from "./ResearchStepPanel";
import { taskSchema } from "./draft";
import * as network from "./api";
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const task = taskSchema.parse({
  id: "t",
  project_id: "p",
  revision: 5,
  updated: 1,
  draft: {
    title: "研究",
    purpose: "assessment",
    selection: [],
    mapping: [],
    options: {},
  },
});
const items = Array.from({ length: 30 }, (_, i) => ({
  id: String(i),
  name: `保留完整科学标识的长图层名称_${i}`,
  kind: "栅格",
  role: i ? "indicator" : "composite",
  visible: i === 0,
}));
test("30 layers: filtering, selecting and bulk checks cannot toggle display or run computation", () => {
  const onSelect = vi.fn(),
    onVisibility = vi.fn(),
    onRemove = vi.fn(),
    onOrder = vi.fn();
  render(
    <LayerCatalog
      items={items}
      activeId="0"
      onSelect={onSelect}
      onVisibility={onVisibility}
      onRemove={onRemove}
      onOrder={onOrder}
      onAction={vi.fn()}
    />,
  );
  expect(screen.queryByLabelText("批选 " + items[0]!.name)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: items[3]!.name }));
  expect(onSelect).toHaveBeenCalledWith("3");
  expect(onVisibility).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("搜索当前图层"), {
    target: { value: "_29" },
  });
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
  expect(onVisibility).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "管理" }));
  fireEvent.click(screen.getByLabelText("批选筛选图层"));
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(onVisibility).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "移出地图 (1)" }));
  expect(onRemove).toHaveBeenCalledWith(["29"]);
  fireEvent.change(screen.getByLabelText("搜索当前图层"), {
    target: { value: "" },
  });
  fireEvent.click(screen.getByLabelText("显示 " + items[0]!.name));
  expect(onVisibility).toHaveBeenCalledWith("0", false);
  expect(onOrder).not.toHaveBeenCalled();
});
test("manual tab survives preferred-step changes, input view is separate from binding", () => {
  const inspect = vi.fn(),
    remove = vi.fn(),
    view = vi.fn();
  const asset = network.assetSchema.parse({
    id: "a",
    project_id: "p",
    name: "真实观测.csv",
    size: 10,
    sha256: "x",
    revision: 1,
    facts: { profile: "csv", standard_version: null, layers: [], issues: [] },
  });
  const props = {
    assets: [asset],
    runCount: 2,
    viewedRun: "r",
    onInspect: inspect,
    onRemove: remove,
    onAdd: vi.fn(),
    onViewRun: view,
    canEdit: false,
  };
  const { rerender } = render(
    <ResearchContentManager {...props} preferredTab="layers">
      <p>图层原状态</p>
    </ResearchContentManager>,
  );
  fireEvent.click(screen.getByRole("tab", { name: "输入 1" }));
  fireEvent.click(screen.getByRole("button", { name: "真实观测.csv" }));
  expect(inspect).toHaveBeenCalledWith("a");
  expect(remove).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "移除输入 真实观测.csv" }),
  ).toBeDisabled();
  rerender(
    <ResearchContentManager {...props} runCount={3} preferredTab="layers">
      <p>图层原状态</p>
    </ResearchContentManager>,
  );
  expect(screen.getByRole("tab", { name: "输入 1" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(view).not.toHaveBeenCalled();
});
test("viewing fixed config uses frozen v4, has no automatic preflight or mutation", async () => {
  const api = vi.spyOn(network, "api");
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const frozen = {
    ...task.draft,
    title: "历史",
    selection: [{ asset_id: "old", revision: 1 }],
    mapping: [
      {
        asset_id: "old",
        field: "old_field",
        unit: "m",
        concept: "旧定义",
        support: "grid",
        template_id: null,
        role: "feature",
      },
    ],
  };
  const job = {
    id: "r",
    status: "succeeded",
    manifest: {
      draft_revision: 4,
      draft: frozen,
      assets: [
        { id: "old", name: "历史输入", revision: 1, facts: { profile: "csv" } },
      ],
    },
  };
  render(
    <QueryClientProvider client={client}>
      <ResearchStepPanel
        step="indicators"
        scope="run"
        task={task}
        assets={[]}
        job={job}
        onScope={vi.fn()}
      />
    </QueryClientProvider>,
  );
  expect(screen.getByText(/配置 v4/)).toBeVisible();
  fireEvent.click(screen.getByText("来源字段"));
  expect(screen.getByText(/old_field/)).toBeVisible();
  await waitFor(() => expect(api).not.toHaveBeenCalled());
  expect(stepStatus("sources", "run", task, job).label).toBe("已引用");
  expect(stepStatus("sources", "draft", task, job).label).toBe("待补");
  expect(stepStatus("synthesis", "draft", task, job).label).toBe("待核查");
  expect(stepStatus("validation", "run", task, job).label).toBe("待验证");
  client.clear();
});

test("two-character rail labels keep the full accessible scientific step titles", () => {
  expect(researchSteps.map((step) => step.label)).toEqual([
    "数据",
    "对齐",
    "指标",
    "权评",
    "综合",
    "分级",
    "时空",
    "成果",
  ]);
  expect(researchSteps.map((step) => step.title)).toEqual([
    "数据",
    "准备与对齐",
    "指标",
    "权重与评价",
    "综合计算",
    "分级",
    "时空分析",
    "成果",
  ]);
});
