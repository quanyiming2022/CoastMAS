import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import AssessmentResults from "./AssessmentResults";
vi.mock("./Chart", () => ({ default: () => <div>时间图</div> }));
it("changes periods and filters units without mixing another unit's scores", () => {
  render(
    <AssessmentResults
      view={{
        binding_status: "UNBOUND",
        entity_binding: [],
        unbound_objects: ["a", "b"],
        objects: ["U1", "U2"].map((unit, index) => ({
          id: index ? "b" : "a",
          node_id: "node",
          variable: "scores",
          standard_name: "assessment_scores",
          model: { id: "model", version: 1 },
          management_unit_id: unit,
          source_pointer: "/outputs/node.scores",
          values: {
            years: [2020, 2025],
            scores: index ? [0.3, 0.8] : [0, 0.4],
            classes: [0, 1],
          },
          units: { scores: "1" },
        })),
      }}
    />,
  );
  const table = screen.getByRole("table", { name: "所选年份评价结果" });
  expect(
    within(table).getAllByText("0", { exact: true }).length,
  ).toBeGreaterThan(0);
  fireEvent.change(screen.getByLabelText("查看评价年份"), {
    target: { value: "1" },
  });
  fireEvent.change(screen.getByLabelText("评价管理单元"), {
    target: { value: "a" },
  });
  expect(within(table).getAllByRole("row")).toHaveLength(2);
  expect(within(table).getByText("2025")).toBeInTheDocument();
  expect(within(table).getByText("0.4")).toBeInTheDocument();
  expect(within(table).queryByText("0.8")).toBeNull();
});
