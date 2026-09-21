import { DataTable } from "./components";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { request, dashboardSchema } from "./api";
import { useWorkspace } from "./workspace";
import {
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";

const countLabels: [string, string, string][] = [
  ["scenes", "场景", "/scenes"],
  ["models", "模型", "/models"],
  ["executable_models", "可执行模型", "/models"],
  ["workflows", "工作流", "/workflows"],
  ["data_assets", "数据资产", "/data"],
  ["results", "结果版本", "/results"],
];
export default function Dashboard() {
  const { projectId } = useWorkspace();
  const query = useQuery({
    queryKey: ["dashboard", projectId],
    queryFn: ({ signal }) =>
      request(
        "/dashboard?project_id=" + encodeURIComponent(projectId),
        dashboardSchema,
        { signal },
      ),
    refetchInterval: 10000,
  });
  return (
    <>
      <PageTitle
        title="项目概览"
        description="从真实数据出发，规划、验证并运行可复现的海岸带分析。"
      />
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      {query.data ? (
        <>
          <div className="metrics">
            {countLabels.map(([key, label, path]) => (
              <Link className="metric" to={path} key={key}>
                <span>{label}</span>
                <strong>{query.data.counts[key] ?? 0}</strong>
                <small>查看详情 →</small>
              </Link>
            ))}
          </div>
          <div className="two-columns">
            <Panel title="最近运行">
              {query.data.recent_runs.length ? (
                <DataTable>
                  <thead>
                    <tr>
                      <th>任务</th>
                      <th>状态</th>
                      <th className="numeric">进度</th>
                    </tr>
                  </thead>
                  <tbody>
                    {query.data.recent_runs.map((run) => (
                      <tr key={run.id}>
                        <td>
                          <Link to={"/runs/" + encodeURIComponent(run.id)}>
                            {run.id.slice(0, 8)}
                          </Link>
                        </td>
                        <td>
                          <Status value={run.status} />
                        </td>
                        <td className="numeric">
                          {Math.round(run.progress * 100)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              ) : (
                <Empty>
                  尚无运行记录。打开工作流，完成预检后即可提交计算。
                </Empty>
              )}
            </Panel>
            <Panel title="规划与质量">
              <p>
                确定性模板可独立使用。模型运行仍需通过数据、单位、坐标、时间与权限检查。
              </p>
              <p>
                <Status
                  value={
                    query.data.provider_configured ? "可用" : "未配置外部 LLM"
                  }
                />
              </p>
              <p className="muted">
                已验证模型的资格不等于新场景运行已通过预检。
              </p>
              <Link className="button secondary" to="/workflows">
                打开工作流
              </Link>
            </Panel>
          </div>
        </>
      ) : null}
    </>
  );
}
