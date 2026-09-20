import { lazy, Suspense, useState } from "react";
import type { ResultView } from "./generated/contracts";
import { assessmentGroups, type AssessmentGroup } from "./assessment-data";
import { ErrorNotice, Loading, Panel } from "./components";
const Chart = lazy(() => import("./Chart"));

export default function AssessmentResults({ view }: { view: ResultView }) {
  let groups: AssessmentGroup[];
  try {
    groups = assessmentGroups(view.objects);
  } catch (error) {
    return <ErrorNotice error={error} />;
  }
  return (
    <>
      {groups.map((group) => (
        <AssessmentPeriod key={group.id} group={group} />
      ))}
    </>
  );
}
function AssessmentPeriod({ group }: { group: AssessmentGroup }) {
  const [selectedPeriod, setSelectedPeriod] = useState(0);
  const [selectedUnit, setSelectedUnit] = useState("*");
  const period = Math.min(selectedPeriod, (group.years?.length ?? 1) - 1);
  const visible =
    selectedUnit === "*"
      ? group.series
      : group.series.filter((item) => item.objectId === selectedUnit);
  const temporal = group.years !== null && group.years.length > 1;
  return (
    <Panel title={temporal ? "多期评价与时间序列" : "单期评价"}>
      <p className="break">{group.label}</p>
      <p>
        分数基于该次固定评价框架，单位为无量纲；等级来自模型输出，不代表通用管理标准。
      </p>
      <label>
        评价管理单元
        <select
          value={selectedUnit}
          onChange={(event) => setSelectedUnit(event.target.value)}
        >
          <option value="*">全部管理单元</option>
          {group.series.map((item) => (
            <option key={item.objectId} value={item.objectId}>
              {item.unitId}
            </option>
          ))}
        </select>
      </label>
      {group.years ? (
        <label>
          查看评价年份
          <select
            value={period}
            onChange={(event) => setSelectedPeriod(Number(event.target.value))}
          >
            {group.years.map((year, index) => (
              <option value={index} key={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p>此结果未声明年份，不推断为当前年份。</p>
      )}
      <Suspense fallback={<Loading />}>
        {temporal ? (
          <Chart
            labels={group.years!.map(String)}
            coordinates={group.years!}
            series={visible.map((item) => ({
              name: item.unitId,
              values: item.scores,
            }))}
            unit="1"
            type="line"
          />
        ) : (
          <Chart
            labels={visible.map((item) => item.unitId)}
            series={[
              {
                name: "评价分数",
                values: visible.map((item) => item.scores[0]!),
              },
            ]}
            unit="1"
          />
        )}
      </Suspense>
      <div className="table-scroll">
        <table aria-label="所选年份评价结果">
          <thead>
            <tr>
              <th>管理单元</th>
              <th>年份</th>
              <th>分数（1）</th>
              <th>等级</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.objectId}>
                <td>{item.unitId}</td>
                <td>{group.years?.[period] ?? "未声明"}</td>
                <td>{item.scores[period]}</td>
                <td>{item.classes[period]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {temporal ? (
        <details>
          <summary>完整时间序列表</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>年份</th>
                  {visible.map((item) => (
                    <th key={item.objectId}>{item.unitId} 分数（1）</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {group.years!.map((year, index) => (
                  <tr key={year}>
                    <td>{year}</td>
                    {visible.map((item) => (
                      <td key={item.objectId}>{item.scores[index]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ) : null}
    </Panel>
  );
}
