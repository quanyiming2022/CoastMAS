import { useEffect, useRef } from "react";
import { init, use as registerCharts } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
registerCharts([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  SVGRenderer,
]);
export interface ChartSeries {
  name: string;
  values: number[];
}
export default function Chart({
  labels,
  series,
  unit,
  type = "bar",
}: {
  labels: string[];
  series: ChartSeries[];
  unit: string;
  type?: "bar" | "line";
}) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = init(element.current, undefined, { renderer: "svg" });
    chart.setOption({
      color: ["#138a8b", "#c7a45d", "#7285b7"],
      tooltip: { trigger: "axis", renderMode: "richText" },
      legend: { bottom: 0 },
      grid: { left: 55, right: 25, top: 35, bottom: 55 },
      xAxis: { type: "category", data: labels },
      yAxis: { type: "value", name: unit },
      series: series.map((item) => ({
        name: item.name,
        type,
        data: item.values,
        barMaxWidth: 50,
        connectNulls: false,
      })),
    });
    const resize = new ResizeObserver(() => chart.resize());
    resize.observe(element.current);
    return () => {
      resize.disconnect();
      chart.dispose();
    };
  }, [labels, series, unit, type]);
  return (
    <div
      ref={element}
      className="result-chart"
      role="img"
      aria-label={
        series.map((item) => item.name).join("、") + "，单位：" + unit
      }
    />
  );
}
