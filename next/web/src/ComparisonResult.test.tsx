import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ComparisonResult } from "./ComparisonResult";
afterEach(cleanup);
const data = {
  scope: "immutable_result_comparison",
  comparable: true,
  basis: "同一资料权重敏感性；不代表时间变化。",
  mode: "method_sensitivity",
  differences: [{ field: "weights", left: [0.5, 0.5], right: [0.2, 0.8] }],
  adaptations: [],
  inputs: [],
  rows: Array.from({ length: 26 }, (_, i) => ({
    id: String(i).padStart(3, "0"),
    left: 0,
    right: 0,
    difference: 0,
    unit: "1",
  })),
};
it("paginates complete identity-aligned results and preserves zero", () => {
  render(<ComparisonResult data={data} />);
  expect(screen.getByText("000")).toBeTruthy();
  expect(screen.queryByText("025")).toBeNull();
  expect(screen.getAllByRole("cell", { name: "0" }).length).toBe(75);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByText("025")).toBeTruthy();
  expect(screen.getByText("2 / 2 页 · 共 26 条")).toBeTruthy();
  expect(screen.getByText("指标权重")).toBeTruthy();
});
it("never renders numeric rows when comparability was not established", () => {
  render(<ComparisonResult data={{ ...data, comparable: false }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("不具备可比性");
  expect(screen.queryByRole("table")).toBeNull();
});
it("selection booleans remain explicit rather than disappearing or becoming scores", () => {
  render(
    <ComparisonResult
      data={{
        ...data,
        mode: "constraint_sensitivity",
        rows: [
          {
            id: "001",
            left: false,
            right: true,
            difference: 1,
            unit: "selection",
          },
        ],
      }}
    />,
  );
  expect(screen.getByText("未选")).toBeTruthy();
  expect(screen.getByText("已选")).toBeTruthy();
  expect(screen.getByText("新增选择")).toBeTruthy();
});
