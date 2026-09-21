import { DataTable } from "./components";
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, jobSchema, resultSchema } from "./api";
import {
  Details,
  display,
  Empty,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";
import { useWorkspace } from "./workspace";

export default function Runs() {
  const { projectId } = useWorkspace();
  const query = useQuery({
    queryKey: ["jobs", projectId],
    queryFn: ({ signal }) =>
      request(
        "/jobs?project_id=" + encodeURIComponent(projectId),
        z.array(jobSchema),
        { signal },
      ),
    refetchInterval: 5000,
  });
  return (
    <>
      <PageTitle
        title="运行中心"
        description="跟踪真实计算任务、进度和失败原因。"
      />
      {query.isPending ? <Loading /> : null}
      <ErrorNotice error={query.error} />
      <Panel title="最近任务">
        {query.data?.length ? (
          <DataTable>
            <thead>
              <tr>
                <th>任务</th>
                <th>状态</th>
                <th className="numeric">进度</th>
                <th className="numeric">执行尝试</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((job) => (
                <tr key={job.id}>
                  <td>
                    <Link to={"/runs/" + encodeURIComponent(job.id)}>
                      {job.id.slice(0, 12)}
                    </Link>
                  </td>
                  <td>
                    <Status value={job.status} />
                  </td>
                  <td className="numeric">{Math.round(job.progress * 100)}%</td>
                  <td className="numeric">{job.attempt}</td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        ) : query.data ? (
          <Empty>尚无任务。请从工作流提交运行。</Empty>
        ) : null}
      </Panel>
    </>
  );
}
export function RunDetail() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  const client = useQueryClient();
  const navigate = useNavigate();
  const retryKey = useRef(crypto.randomUUID());
  const query = useQuery({
    queryKey: ["job", projectId, id],
    queryFn: ({ signal }) =>
      request("/jobs/" + encodeURIComponent(id), jobSchema, { signal }),
    refetchInterval: (query) =>
      query.state.data &&
      ["SUCCEEDED", "FAILED", "CANCELLED"].includes(query.state.data.status)
        ? false
        : 1500,
  });
  const results = useQuery({
    queryKey: ["job-results", projectId, id],
    queryFn: ({ signal }) =>
      request(
        "/results?project_id=" + encodeURIComponent(projectId),
        z.array(resultSchema),
        { signal },
      ),
    enabled: query.data?.status === "SUCCEEDED",
  });
  const cancel = useMutation({
    mutationFn: () =>
      request("/jobs/" + encodeURIComponent(id) + "/cancel", jobSchema, {
        method: "POST",
      }),
    onSuccess: (job) => {
      client.setQueryData(["job", projectId, id], job);
    },
  });
  const retry = useMutation({
    mutationFn: () =>
      request("/jobs/" + encodeURIComponent(id) + "/retry", jobSchema, {
        method: "POST",
        idempotencyKey: retryKey.current,
      }),
    onSuccess: (job) => {
      navigate("/runs/" + encodeURIComponent(job.id));
    },
  });
  const job = query.data;
  return (
    <>
      <Link to="/runs">← 返回运行中心</Link>
      <PageTitle title="任务详情" description={id} />
      {query.isPending ? <Loading /> : null}
      <ErrorNotice
        error={query.error ?? cancel.error ?? retry.error ?? results.error}
      />
      {job ? (
        <>
          <Panel title="计算状态">
            <div className="toolbar">
              <Status value={job.status} />
              <progress aria-label="运行进度" value={job.progress} max={1} />
              <span>{Math.round(job.progress * 100)}%</span>
              {["QUEUED", "RUNNING"].includes(job.status) ? (
                <button
                  disabled={cancel.isPending || job.cancel_requested}
                  onClick={() => cancel.mutate()}
                >
                  {job.cancel_requested ? "正在取消…" : "取消任务"}
                </button>
              ) : null}
              {["FAILED", "CANCELLED"].includes(job.status) ? (
                <button
                  disabled={
                    retry.isPending ||
                    job.error?.error_code === "REMOTE_STATUS_UNKNOWN"
                  }
                  onClick={() => retry.mutate()}
                >
                  按原快照重试
                </button>
              ) : null}
            </div>
            {job.error ? (
              <div role="alert" className="error">
                <strong>{display(job.error.error_code)}</strong>
                <p>{display(job.error.message)}</p>
              </div>
            ) : null}
            {results.data
              ?.filter((result) => result.job_id === id)
              .map((result) => (
                <Link
                  className="button"
                  key={result.id}
                  to={
                    job.manifest.kind === "research_evaluation"
                      ? "/research/" + encodeURIComponent(job.id)
                      : "/results/" + encodeURIComponent(result.id)
                  }
                >
                  查看不可变结果
                </Link>
              ))}
          </Panel>
          <Details title="运行快照与精确版本" value={job.manifest} />
        </>
      ) : null}
    </>
  );
}
