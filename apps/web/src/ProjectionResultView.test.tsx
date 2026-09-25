import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ProjectionResultView, { projectionResult } from "./ProjectionResultView";
afterEach(cleanup);
it("keeps sample scope and real pagination counts rather than treating clusters as ranks", () => {
  const result = projectionResult.parse({
    method: "PPCI::mcdc",
    row_ids: Array.from({ length: 24 }, (_, i) => `r0c${i}`),
    cluster: Array.from({ length: 24 }, () => 2),
    locations: null,
    observation_scope: "sample_only",
    joint_valid_cells: 100000,
    business_validated: false,
  });
  render(<ProjectionResultView result={result} />);
  expect(screen.getByText(/仅样本结果/)).toBeTruthy();
  expect(screen.getByText(/没有好坏等级含义/)).toBeTruthy();
  expect(screen.queryByText("r0c20")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "下一页观测" }));
  expect(screen.getByText("r0c20")).toBeTruthy();
  expect(screen.getByText("第2页 / 2页 · 共24项")).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "下一页观测" }).hasAttribute("disabled"),
  ).toBe(true);
  expect(projectionResult.safeParse({ ...result, cluster: [2] }).success).toBe(
    false,
  );
});
