import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import TemporalResultView from "./TemporalResultView";
import type { TemporalResult } from "./generated/contracts";
afterEach(cleanup);
const result: TemporalResult = {
  variable: "temperature",
  value: 0,
  unit: "degC",
  method: "mean",
  start: "2025-01-01T00:00:00Z",
  end: "2025-01-01T04:00:00Z",
  source_start: "2025-01-01T00:00:00Z",
  source_end: "2025-01-01T04:00:00Z",
  observations_used: 2,
  valid_observations: 2,
  nodata_policy: "propagate",
  interpretation: "Duration-weighted source support means.",
};
it("renders actual zero with its physical unit and observation count", () => {
  render(<TemporalResultView result={result} />);
  expect(screen.getByTestId("temporal-value")).toHaveTextContent("0 degC");
  expect(screen.getByText("2 / 2")).toBeInTheDocument();
});
it("shows missing as unknown, separately from zero", () => {
  render(
    <TemporalResultView
      result={{ ...result, value: null, valid_observations: 1 }}
    />,
  );
  expect(screen.getByTestId("temporal-value")).toHaveTextContent(
    "未知（缺测）",
  );
  expect(screen.getByText("1 / 2")).toBeInTheDocument();
});
