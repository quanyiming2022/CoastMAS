import { afterEach, describe, it, expect } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { ObservationTable, AllocationTable, ResultView } from "./ResultView";
afterEach(cleanup);
describe("complete result table", () => {
  it("paginates actual rows, retains zero and labels sample coverage", () => {
    render(
      <ObservationTable
        data={{
          row_ids: Array.from({ length: 43 }, (_, i) =>
            String(i).padStart(3, "0"),
          ),
          fitted: Array.from({ length: 43 }, (_, i) => i),
          residuals: Array.from({ length: 43 }, () => 0),
          observation_scope: "sample_only",
          joint_valid_cells: 100,
        }}
      />,
    );
    expect(screen.getByText("000")).toBeTruthy();
    expect(
      screen.getByText("训练/观测样本 43 条；共同有效分母 100"),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByText("025")).toBeTruthy();
    expect(screen.queryByText("000")).toBeNull();
    expect(screen.getByText("2 / 2 页 · 共 43 条")).toBeTruthy();
  });
  it("refuses misaligned result columns", () => {
    render(<ObservationTable data={{ row_ids: ["a", "b"], cluster: [1] }} />);
    expect(screen.getByRole("alert").textContent).toContain("数量");
  });
});

it("does not show an infeasible allocation as a rejected or accepted policy decision", () => {
  render(
    <AllocationTable
      data={{
        status: "INFEASIBLE",
        constraints_satisfied: false,
        allocations: [
          {
            id: "001",
            selected: null,
            allowed: true,
            benefit: 9,
            cost: 2,
            area: 3,
            ecological_cost: 0,
            risk: 0,
          },
        ],
      }}
    />,
  );
  expect(
    screen.getByText("尚无满足约束的配置方案", { exact: false }),
  ).toBeTruthy();
  expect(screen.getByText("未形成可行解")).toBeTruthy();
  expect(screen.queryByText("已选入")).toBeNull();
});

it("renders one entity panel across result refreshes", () => {
  const data = {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        id: "001",
        properties: { v: 0 },
        geometry: { type: "Point", coordinates: [113, 23] },
      },
    ],
  };
  const { rerender } = render(<ResultView jobId="same-job" data={data} />);
  rerender(<ResultView jobId="same-job" data={structuredClone(data)} />);
  rerender(<ResultView jobId="same-job" data={structuredClone(data)} />);
  expect(screen.getAllByRole("table", { name: "完整实体属性" })).toHaveLength(
    1,
  );
});

it("nonspatial scores render a table without a fabricated map", () => {
  render(<ResultView jobId="numeric-run" data={{row_ids: ["001", "002"], scores: [.5, 1]}} />);
  expect(screen.getByRole("table", {name: "观测结果"})).toBeTruthy();
  expect(screen.queryByRole("region", {name: /地图/})).toBeNull();
  expect(screen.queryByLabelText("本次实际空间成果")).toBeNull();
});
