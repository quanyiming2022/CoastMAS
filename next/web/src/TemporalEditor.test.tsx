import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { TemporalEditor, TemporalResult } from "./TemporalEditor";
import { draftSchema } from "./draft";
import { assetSchema } from "./api";
afterEach(cleanup);
const draft = draftSchema.parse({
  title: "CF task",
  purpose: "temporal",
  selection: [],
  mapping: [],
  options: { variable: "height", method: "mean", output_unit: "m" },
});
const asset = assetSchema.parse({
  id: "a",
  project_id: "p",
  revision: 1,
  name: "actual.nc",
  sha256: "hash",
  size: 100,
  facts: {
    profile: "netcdf",
    standard_version: "CF-1.12",
    layers: [],
    issues: [],
    temporal_candidates: [
      {
        variable: "height",
        axis: "time",
        method: "mean",
        cell_method: "mean",
        unit: "m",
        calendar: "360_day",
        time_axis_unit: "days since 2022-01-01",
      },
    ],
  },
});
it("keeps file-determined fields and only asks for the target interval", () => {
  const change = vi.fn();
  render(<TemporalEditor draft={draft} assets={[asset]} onChange={change} />);
  expect(screen.getByLabelText("观测变量")).toHaveValue("height");
  expect(screen.getByLabelText("目标方法")).toHaveValue("mean");
  expect(screen.getByLabelText("输出单位")).toHaveValue("m");
  expect(screen.getByText(/360_day/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("开始日期（源日历）"), {
    target: { value: "2022-02-30" },
  });
  expect(change.mock.calls[0]![0].options.start).toBe("2022-02-30");
  expect(screen.queryByLabelText("适配依据")).toBeNull();
});
it("requires user purpose for point adaptation and displays scientific approximation controls", () => {
  const point = {
    ...asset,
    facts: {
      ...asset.facts,
      temporal_candidates: [
        {
          ...asset.facts.temporal_candidates![0]!,
          method: null,
          cell_method: "point",
        },
      ],
    },
  };
  render(
    <TemporalEditor
      draft={{ ...draft, options: { variable: "height", method: "nearest" } }}
      assets={[point]}
      onChange={() => {}}
    />,
  );
  expect(screen.getByLabelText("目标时刻（源日历）")).toBeTruthy();
  expect(screen.getByLabelText("适配依据")).toBeTruthy();
  expect(screen.getByLabelText(/容许偏差/)).toBeTruthy();
  expect(screen.queryByLabelText("开始日期（源日历）")).toBeNull();
});
it("keeps zero, source calendar, unit, scope and approximation visible in results", () => {
  render(
    <TemporalResult
      data={{
        variable: "height",
        value: 0,
        method: "min",
        calendar: "360_day",
        start: "2022-02-01",
        end: "2022-02-30",
        observations: 3,
        scope: "declared_interval",
        conversion: { source_unit: "m", target_unit: "cm" },
        adaptation: {
          approximate: false,
          basis: "complete_declared_source_intervals",
        },
        covered_duration: 29,
        duration_unit: "days",
      }}
    />,
  );
  expect(screen.getByText("0 cm")).toBeTruthy();
  expect(screen.getByText("360_day")).toBeTruthy();
  expect(screen.getByText("2022-02-30")).toBeTruthy();
  expect(screen.getByText("实际覆盖 29 days · 使用 3 条观测")).toBeTruthy();
});
