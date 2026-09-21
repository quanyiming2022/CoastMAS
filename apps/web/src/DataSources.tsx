import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema } from "./api";
import { contractErrors } from "./contracts";
import { dataContract } from "./data-editor";
import {
  freshSource,
  prepareSourceRevision,
  sourceContract,
} from "./source-editor";
import type { DataSourceSpec, JsonValue } from "./generated/contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle, Panel } from "./components";
import DataMetadataForm from "./DataMetadataForm";
const revisionContract = revisionSchema.extend({ spec: sourceContract });
const connectorContract = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["http", "postgresql"]),
  revision: z.number().int().positive(),
});
const jsonRecord = z.record(z.string(), z.json());

export default function DataSources() {
  const { projectId } = useWorkspace();
  return <SourceList key={projectId} projectId={projectId} />;
}
function SourceList({ projectId }: { projectId: string }) {
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const query = useQuery({
    queryKey: ["data-sources", projectId, search, page],
    queryFn: ({ signal }) =>
      request(
        `/data-sources?${new URLSearchParams({ project_id: projectId, q: search, limit: "50", offset: String(page * 50) })}`,
        z.array(revisionContract),
        { signal },
      ),
  });
  return (
    <>
      <PageTitle
        title="外部数据源"
        description="登记已批准的 URL / HTTP 或数据库连接器，导入可复现的文件快照。"
      />
      <div className="toolbar">
        <Link to="/data-sources/new">登记数据源</Link>
        <Link to="/data">返回数据目录</Link>
        <label>
          搜索数据源
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
        </label>
        <button
          onClick={() => {
            setSearch(text.trim());
            setPage(0);
          }}
        >
          搜索
        </button>
      </div>
      <ErrorNotice error={query.error} />
      {query.isPending ? <Loading /> : null}
      {query.data ? (
        <Panel title="已登记数据源">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>来源类型</th>
                <th>版本</th>
              </tr>
            </thead>
            <tbody>
              {query.data.map((row) => (
                <tr key={row.resource_id}>
                  <td>
                    <Link
                      to={`/data-sources/${encodeURIComponent(row.resource_id)}`}
                    >
                      {row.spec.name}
                    </Link>
                  </td>
                  <td>
                    {row.spec.kind === "http" ? "URL / HTTP" : "PostgreSQL"}
                  </td>
                  <td>{row.version}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {query.data.length === 0 ? <p>当前筛选无数据源。</p> : null}
          <div className="toolbar">
            <button disabled={page === 0} onClick={() => setPage(page - 1)}>
              上一页
            </button>
            <span>第 {page + 1} 页</span>
            <button
              disabled={query.data.length < 50}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </button>
          </div>
        </Panel>
      ) : null}
    </>
  );
}
export function SourceEditor() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  return (
    <Editor key={`${projectId}:${id ?? "new"}`} id={id} projectId={projectId} />
  );
}
function Editor({ id, projectId }: { id?: string; projectId: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [fresh] = useState(freshSource);
  const [parameters] = useSearchParams();
  const requestedVersion = Number(parameters.get("version"));
  const [version, setVersion] = useState(
    Number.isInteger(requestedVersion) && requestedVersion > 0
      ? requestedVersion
      : 0,
  );
  const [draft, setDraft] = useState<DataSourceSpec | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const [importKey, setImportKey] = useState(() => crypto.randomUUID());
  const query = useQuery({
    queryKey: ["source-editor", projectId, id, version],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/data-sources/${encodeURIComponent(id!)}${version ? `?version=${version}` : ""}`,
        revisionContract,
        { signal },
      ),
  });
  const history = useQuery({
    queryKey: ["source-history", projectId, id],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/data-sources/${encodeURIComponent(id!)}/versions`,
        z.array(revisionContract),
        { signal },
      ),
  });
  const connectors = useQuery({
    queryKey: ["source-connectors", projectId],
    queryFn: ({ signal }) =>
      request(
        `/data-sources/connectors?project_id=${encodeURIComponent(projectId)}`,
        z.array(connectorContract),
        { signal },
      ),
  });
  const base = query.data?.spec ?? null;
  const current = draft ?? base ?? fresh;
  const [outputDraft, setOutputDraft] = useState<Record<
    string,
    JsonValue
  > | null>(null);
  const output = outputDraft ?? jsonRecord.parse(current.output);
  const changed = draft !== null || outputDraft !== null;
  const historical = version !== 0;
  const save = useMutation({
    mutationFn: () => {
      const candidate = { ...current, output };
      const errors = contractErrors("DataSourceSpec", candidate);
      setIssues(errors);
      if (errors.length) throw new Error("请补全数据源与科学元数据");
      const spec = prepareSourceRevision(candidate, base);
      return request(
        id ? `/data-sources/${encodeURIComponent(id)}` : "/data-sources",
        revisionContract,
        {
          method: id ? "PUT" : "POST",
          body: id
            ? { expected_version: base!.version, spec }
            : { project_id: projectId, spec },
        },
      );
    },
    onSuccess: async (row) => {
      client.setQueryData(
        ["source-editor", projectId, row.resource_id, 0],
        row,
      );
      setDraft(null);
      setOutputDraft(null);
      setVersion(0);
      setImportKey(crypto.randomUUID());
      snapshot.reset();
      setIssues([]);
      navigate(`/data-sources/${encodeURIComponent(row.resource_id)}`, {
        replace: true,
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["data-sources"] }),
        client.invalidateQueries({ queryKey: ["source-history"] }),
      ]);
    },
  });
  const snapshot = useMutation({
    mutationFn: () =>
      request(
        `/data-sources/${encodeURIComponent(id!)}/snapshots`,
        revisionSchema.extend({ spec: dataContract }),
        {
          method: "POST",
          body: { expected_version: base!.version, idempotency_key: importKey },
        },
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ["data"] }),
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/data-sources/${encodeURIComponent(id!)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["data-sources"] });
      navigate("/data-sources");
    },
  });
  const busy = save.isPending || snapshot.isPending || archive.isPending;
  if (id && query.isPending) return <Loading />;
  return (
    <>
      <Link to="/data-sources">← 返回外部数据源</Link>
      <PageTitle
        title={id ? "数据源版本管理" : "登记数据源"}
        description="连接地址与凭证由管理员在本地配置；此处声明数据含义，导入后使用固定文件版本。"
      />
      <ErrorNotice
        error={
          query.error ??
          connectors.error ??
          history.error ??
          save.error ??
          snapshot.error ??
          archive.error
        }
      />
      {issues.length ? (
        <ul role="alert">
          {issues.map((issue, index) => (
            <li key={index}>{issue}</li>
          ))}
        </ul>
      ) : null}
      {id && base ? (
        <Panel title="数据源历史">
          <label>
            查看数据源版本
            <select
              value={version}
              disabled={busy}
              onChange={(event) => {
                setVersion(Number(event.target.value));
                setDraft(null);
                setOutputDraft(null);
                setIssues([]);
                snapshot.reset();
              }}
            >
              <option value={0}>当前版本</option>
              {history.data?.map((row) => (
                <option key={row.version} value={row.version}>
                  版本 {row.version}
                </option>
              ))}
            </select>
          </label>
          <p>显示版本 {base.version}。历史声明只读。</p>
          <button
            disabled={busy || changed || historical}
            onClick={() => snapshot.mutate()}
          >
            {snapshot.isPending ? "正在读取与检查…" : "导入文件快照"}
          </button>
          <button
            className="secondary"
            disabled={busy || changed || historical}
            onClick={() => archive.mutate()}
          >
            归档数据源
          </button>
          <p>已导入快照会保护其来源版本；重复提交同一次导入返回同一快照。</p>
          {snapshot.data && !changed ? (
            <div>
              <Link
                to={`/data/${encodeURIComponent(snapshot.data.resource_id)}/workspace`}
              >
                查看已导入数据
              </Link>
              <button
                onClick={() => {
                  setImportKey(crypto.randomUUID());
                  snapshot.reset();
                }}
              >
                准备下一次导入
              </button>
            </div>
          ) : null}
        </Panel>
      ) : null}
      {!id || base ? (
        <Panel title="连接器与数据声明">
          <fieldset disabled={busy || historical}>
            <label>
              数据源名称
              <input
                value={current.name}
                onChange={(event) =>
                  setDraft({ ...current, name: event.target.value })
                }
              />
            </label>
            <label>
              已批准的连接器
              <select
                value={current.connector_id}
                onChange={(event) => {
                  const selected = connectors.data?.find(
                    (item) => item.id === event.target.value,
                  );
                  if (selected) {
                    setDraft({
                      ...current,
                      connector_id: selected.id,
                      kind: selected.kind,
                    });
                    snapshot.reset();
                  }
                }}
              >
                <option value="">请选择连接器</option>
                {current.connector_id &&
                !connectors.data?.some(
                  (item) => item.id === current.connector_id,
                ) ? (
                  <option value={current.connector_id}>
                    {current.connector_id}（当前不可用）
                  </option>
                ) : null}
                {connectors.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} ·{" "}
                    {item.kind === "http" ? "URL / HTTP" : "PostgreSQL"} ·
                    配置版本 {item.revision}
                  </option>
                ))}
              </select>
            </label>
            {connectors.data?.length === 0 ? (
              <p>
                此项目尚无已批准连接器。管理员可按数据源配置文档添加明确目标，凭证通过环境变量引用。
              </p>
            ) : null}
            {current.kind === "postgresql" ? (
              <p>
                数据库连接器只读导出 CSV；请选择 table /
                CSV，并声明字段的单位和含义。
              </p>
            ) : null}
            <DataMetadataForm values={output} onChange={setOutputDraft} />
            <button
              disabled={busy || historical || !current.connector_id}
              onClick={() => save.mutate()}
            >
              保存数据源版本
            </button>
          </fieldset>
        </Panel>
      ) : null}
    </>
  );
}
