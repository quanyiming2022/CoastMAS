import type { ResearchReport } from "./generated/contracts";
import { Details, Panel } from "./components";

const origins: Record<string, string> = {
  RULE: "规则",
  LOCAL: "本地提供方",
  EXTERNAL: "外部提供方",
  MOCK: "模拟协议",
  REPLAY: "历史回放",
};
const experiments = {
  A: "A · 规则规划",
  B: "B · LLM 推荐",
  C: "C · LLM + 知识图谱 + 约束",
};
const statuses = {
  COMPLETE: "评估完成",
  PARTIAL: "部分完成",
  BLOCKED: "全部阻塞",
};
function percent(value: number | null) {
  return value === null ? "未观测" : `${(value * 100).toFixed(1)}%`;
}
function number(value: number | null) {
  return value === null ? "未观测" : String(value);
}
function verdict(value: boolean | null) {
  return value === null ? "未观测" : value ? "是" : "否";
}

export default function ResearchReportView({
  report,
}: {
  report: ResearchReport;
}) {
  return (
    <>
      <Panel title="科研评估报告">
        <p>
          <strong>{statuses[report.status]}</strong> · 总耗时{" "}
          {report.elapsed_seconds.toFixed(3)} 秒
        </p>
        <p>
          本报告评估规划候选，未执行候选模型。任务完成不代表所有试验通过；来源分开统计，缺测不补零。
        </p>
        <div className="table-scroll">
          <table aria-label="科研分组统计">
            <thead>
              <tr>
                <th>实验</th>
                <th>来源</th>
                <th>已评估 / 总数</th>
                <th>阻塞 / 失败</th>
                <th>完成率</th>
                <th>工作流有效率</th>
                <th>约束违规率 / 观测数</th>
                <th>人工修订次数 / 观测数</th>
                <th>平均耗时（秒）</th>
                <th>实际请求</th>
                <th>提供方 token</th>
              </tr>
            </thead>
            <tbody>
              {report.metrics.map((m) => (
                <tr key={`${m.experiment}:${m.origin}`}>
                  <td>{experiments[m.experiment]}</td>
                  <td>{origins[m.origin]}</td>
                  <td>
                    {m.evaluated} / {m.total}
                  </td>
                  <td>
                    {m.blocked} / {m.failed}
                  </td>
                  <td>{percent(m.evaluation_completion_rate)}</td>
                  <td>{percent(m.workflow_validity_rate)}</td>
                  <td>
                    <span>{percent(m.constraint_violation_rate)}</span> /{" "}
                    {m.constraint_observations}
                  </td>
                  <td>
                    <span>{number(m.manual_correction_count)}</span> /{" "}
                    {m.manual_observations}
                  </td>
                  <td>
                    {m.mean_latency_seconds === null
                      ? "未观测"
                      : m.mean_latency_seconds.toFixed(3)}
                  </td>
                  <td>{m.provider_requests}</td>
                  <td>{number(m.total_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          有效率分母是实际已评估试验；约束违规率只统计实际候选。请同时检查完成率和各项观测数。
        </p>
      </Panel>
      <Panel title="逐项试验与证据">
        <div className="table-scroll">
          <table aria-label="科研逐项试验">
            <thead>
              <tr>
                <th>样例 / 重复</th>
                <th>实验 / 来源</th>
                <th>状态</th>
                <th>存在候选</th>
                <th>科学有效</th>
                <th>诊断</th>
              </tr>
            </thead>
            <tbody>
              {report.trials.map((t) => {
                const r = t.observation;
                return (
                  <tr
                    key={`${r.case_id}:${r.repetition}:${r.experiment}:${r.origin}`}
                  >
                    <td>
                      {r.case_id} / {r.repetition}
                    </td>
                    <td>
                      {experiments[r.experiment]}
                      <br />
                      {origins[r.origin]}
                    </td>
                    <td>
                      {
                        {
                          EVALUATED: "已评估",
                          BLOCKED: "阻塞",
                          FAILED: "失败",
                        }[r.status]
                      }
                    </td>
                    <td>{verdict(r.candidate_present)}</td>
                    <td>{verdict(r.workflow_valid)}</td>
                    <td>
                      {r.diagnostics.map((d, i) => (
                        <p key={i}>{d}</p>
                      ))}
                      <Details title="候选、用量与追踪" value={t} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
