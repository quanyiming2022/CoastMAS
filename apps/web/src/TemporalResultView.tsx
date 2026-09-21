import type { TemporalResult } from "./generated/contracts";
import { temporalMethods } from "./temporal-editor";
export default function TemporalResultView({
  result,
}: {
  result: TemporalResult;
}) {
  return (
    <section aria-label="时间适配结果">
      <dl className="definition-grid">
        <div>
          <dt>物理变量</dt>
          <dd>{result.variable}</dd>
        </div>
        <div>
          <dt>计算值</dt>
          <dd data-testid="temporal-value">
            {result.value === null
              ? "未知（缺测）"
              : `${result.value} ${result.unit}`}
          </dd>
        </div>
        <div>
          <dt>适配方法</dt>
          <dd>{temporalMethods[result.method]}</dd>
        </div>
        <div>
          <dt>有效 / 使用观测数</dt>
          <dd>
            {result.valid_observations} / {result.observations_used}
          </dd>
        </div>
        <div>
          <dt>目标时间（UTC）</dt>
          <dd>
            {result.start} — {result.end}
          </dd>
        </div>
        <div>
          <dt>使用的源观测范围（UTC）</dt>
          <dd>
            {result.source_start} — {result.source_end}
          </dd>
        </div>
        <div>
          <dt>缺测策略</dt>
          <dd>
            {result.nodata_policy === "propagate" ? "传播缺测" : "拒绝缺测"}
          </dd>
        </div>
      </dl>
      <p>
        {result.method === "mean"
          ? "区间值按实际时长加权平均。"
          : result.method === "sum"
            ? "完整区间累计值各计一次。"
            : result.method === "min" || result.method === "max"
              ? "仅描述观测支撑值的极值，不代表未观测时段的连续极值。"
              : "依据实际点观测进行赋值或内插；不外推，不填补缺测。"}
      </p>
    </section>
  );
}
