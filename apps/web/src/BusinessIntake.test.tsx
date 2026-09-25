import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import BusinessIntake from "./BusinessIntake";

afterEach(cleanup);
const report = {
  kind: "coastmas_business_intake",
  version: 1,
  generated_at: "2026-09-23T00:00:00Z",
  source_name: "data_quan",
  scientific_execution_ready: false,
  r_runtime_available: false,
  file_count: 1,
  rasters: [
    {
      path: "TN/example.tif",
      size_bytes: 100,
      sha256: "a".repeat(64),
      width: 3,
      height: 2,
      bands: 1,
      dtype: "int8",
      crs: "EPSG:4326",
      grid_id: "b".repeat(64),
      unit: null,
      observed_period: null,
      statistics_scope: "full",
      valid_cells: 5,
      nodata_cells: 1,
      sample_cells: 6,
      sample_valid_cells: 5,
      minimum: 0,
      maximum: 1,
      value_counts: [
        { value: 0, count: 4 },
        { value: 1, count: 1 },
      ],
      issues: ["GEOGRAPHIC_BOUNDS_INVALID", "UNIT_UNDECLARED"],
    },
  ],
  models: [],
  errors: [],
  skipped_symlinks: [],
  sidecars: [],
};
it("keeps zero values, explains invalid CRS and never calls inspection scientific approval", async () => {
  render(
    <MemoryRouter>
      <BusinessIntake />
    </MemoryRouter>,
  );
  const file = { size: 100, text: async () => JSON.stringify(report) };
  fireEvent.change(screen.getByLabelText("选择业务资料检查报告"), {
    target: { files: [file] },
  });
  await screen.findByText("TN/example.tif");
  expect(screen.getByText(/经纬度坐标超出合法范围/)).toBeTruthy();
  expect(screen.getByText("0 × 4；1 × 1")).toBeTruthy();
  expect(screen.getByText(/检查报告不等于数据已导入/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /提交运行/ })).toBeNull();
});
it("rejects unrelated JSON and clears prior report on failure", async () => {
  render(
    <MemoryRouter>
      <BusinessIntake />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("选择业务资料检查报告"), {
    target: { files: [{ size: 2, text: async () => "{}" }] },
  });
  await screen.findByRole("alert");
  expect(screen.queryByText("TN/example.tif")).toBeNull();
});
