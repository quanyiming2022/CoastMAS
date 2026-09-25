import { afterEach, it, expect, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { EntityResults } from "./EntityResults";

afterEach(cleanup);
vi.mock("./VectorMap", () => ({
  default: ({ selected }: { selected: string | null }) => (
    <div aria-label="测试地图选择">{selected}</div>
  ),
}));
const result = {
  type: "FeatureCollection",
  sources: [{ target_crs: "EPSG:4326" }],
  features: Array.from({ length: 26 }, (_, i) => ({
    type: "Feature",
    id: String(i).padStart(3, "0"),
    geometry: { type: "Point", coordinates: [110 + i / 100, 23] },
    properties:
      i === 25
        ? { later_field: "末条特有属性" }
        : { pressure: 0, protected: false, missing: null },
  })),
};
it("shows all property columns and pages actual entities while preserving zero, false and missing", async () => {
  render(<EntityResults data={result} />);
  expect(
    screen.getByRole("columnheader", { name: "later_field" }),
  ).toBeTruthy();
  expect(screen.getAllByText("0")).toHaveLength(25);
  expect(screen.getAllByText("否")).toHaveLength(25);
  expect(screen.getAllByText("缺值").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getByRole("cell", { name: "025" })).toBeTruthy();
  expect(screen.getByText("末条特有属性")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "在地图定位 025" }));
  expect(await screen.findByLabelText("测试地图选择")).toHaveTextContent("025");
  expect(
    screen.getByRole("button", { name: "在地图定位 025" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("2 / 2 页 · 共 26 条")).toBeTruthy();
});
it("rejects duplicated entity identity rather than showing mismatched selections", () => {
  render(
    <EntityResults
      data={{ ...result, features: [result.features[0], result.features[0]] }}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("标识重复");
});
it("distinguishes a real empty entity collection", () => {
  render(<EntityResults data={{ ...result, features: [] }} />);
  expect(screen.getByText("没有地理实体")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "查看实体地图" })).toBeNull();
});

it("actual located results display their map by default", async () => {
  render(<EntityResults data={{...result, theme_property: "assessment_score"}} />);
  expect(await screen.findByLabelText("测试地图选择")).toBeTruthy();
  expect(screen.getByRole("button", {name: "收起实体地图"})).toBeTruthy();
});
