export type LegendCategory = { value: number; label: string; color: string };
export function legendRange(minimum: number | null, maximum: number | null) {
  if (minimum === null || maximum === null)
    return { single: false, text: "预览样本无有效值" };
  const number = (value: number, precision: number) =>
    Number(value.toPrecision(precision)).toString();
  if (minimum === maximum)
    return { single: true, text: `预览样本值${number(minimum, 8)}` };
  let precision = 6;
  while (
    precision < 17 &&
    number(minimum, precision) === number(maximum, precision)
  )
    precision++;
  return {
    single: false,
    text: `${number(minimum, precision)} — ${number(maximum, precision)}`,
  };
}
export function MapLegend({
  title,
  minimum,
  maximum,
  unit,
  categories,
  compact = false,
}: {
  title: string;
  minimum: number | null;
  maximum: number | null;
  unit: string | null;
  categories?: LegendCategory[];
  compact?: boolean;
}) {
  const range = legendRange(minimum, maximum);
  return (
    <section
      className={compact ? "map-legend-compact" : "map-legend-full"}
      aria-label={compact ? "地图图例" : "完整图例"}
    >
      <strong title={title} tabIndex={0}>
        {title}
      </strong>
      {categories?.length ? (
        <ul className="legend-categories">
          {categories.map((item) => (
            <li key={item.value}>
              <i style={{ background: item.color }} aria-hidden="true" />
              {item.value} · {item.label}
            </li>
          ))}
        </ul>
      ) : (
        <>
          {minimum !== null ? (
            <span
              className={
                range.single ? "legend-single-swatch" : "continuous-legend"
              }
              aria-hidden="true"
            />
          ) : null}
          <span className="legend-values">
            {range.text} {unit === "1" ? "无量纲" : (unit ?? "单位未声明")}
          </span>
        </>
      )}
      {compact ? (
        <details>
          <summary>预览样本</summary>
          <p>仅为显示样本的值域；不代表全域统计。完整依据在样式和详情查看。</p>
        </details>
      ) : (
        <p>
          仅依据固定显示样本，不由显示值域推断全域恒定或科学有效性。色带、显隐和图例偏好不改变原始值与计算。
        </p>
      )}
    </section>
  );
}
