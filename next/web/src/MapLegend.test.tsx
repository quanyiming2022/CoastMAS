import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { MapLegend, legendRange } from "./MapLegend";
afterEach(cleanup);
test("real constant sample is a single swatch, never a claim about the whole raster", () => {
  expect(legendRange(0.375, 0.375)).toEqual({
    single: true,
    text: "预览样本值0.375",
  });
  render(
    <MapLegend
      title="固定运行指标"
      minimum={0.375}
      maximum={0.375}
      unit="1"
      compact
    />,
  );
  expect(screen.getByText("预览样本值0.375 无量纲")).toBeVisible();
  expect(document.querySelector(".legend-single-swatch")).not.toBeNull();
  expect(document.querySelector(".continuous-legend")).toBeNull();
  expect(screen.queryByText(/全域恒定/)).toBeNull();
});
test("rounded equal ends gain precision without inventing a range", () => {
  const r = legendRange(0.37500001, 0.37500002);
  expect(r.single).toBe(false);
  expect(r.text).toContain("0.37500001");
  expect(r.text).toContain("0.37500002");
  expect(legendRange(null, null).text).toBe("预览样本无有效值");
});
test("all categories remain available inside the scrolling legend", () => {
  render(
    <MapLegend
      title="质量分类"
      minimum={0}
      maximum={29}
      unit="1"
      compact
      categories={Array.from({ length: 30 }, (_, i) => ({
        value: i,
        label: "类别" + i,
        color: "#123456",
      }))}
    />,
  );
  expect(screen.getAllByRole("listitem")).toHaveLength(30);
  expect(screen.getByText("29 · 类别29")).toBeInTheDocument();
});
