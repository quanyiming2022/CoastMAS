import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import schema from "../contracts.schema.json";
import { request, revisionSchema } from "./api";
import { contract, contractErrors } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  dataContract,
  freshData,
  prepareDataRevision,
  newDataVariable,
} from "./data-editor";
import { modelFieldOptions } from "./model-editor";
import type { JsonValue } from "./generated/contracts";
import ScientificFields from "./ScientificFields";
import {
  Details,
  ErrorNotice,
  Loading,
  PageTitle,
  Panel,
  Status,
} from "./components";
const revisionContract = revisionSchema.extend({ spec: dataContract });
const previewContract = contract("DataInspection");
export default function DataWorkspace() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  return (
    <Workspace
      key={`${projectId}:${id ?? "new"}`}
      id={id}
      projectId={projectId}
    />
  );
}
function Workspace({ id, projectId }: { id?: string; projectId: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [fresh] = useState(freshData);
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState<Record<string, JsonValue> | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [issues, setIssues] = useState<string[]>([]);
  const key = ["data-workspace", projectId, id, version];
  const query = useQuery({
    queryKey: key,
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/data-assets/${encodeURIComponent(id!)}${version ? `?version=${version}` : ""}`,
        revisionContract,
        { signal },
      ),
  });
  const history = useQuery({
    queryKey: ["data-history", projectId, id],
    enabled: !!id,
    queryFn: ({ signal }) =>
      request(
        `/data-assets/${encodeURIComponent(id!)}/versions`,
        z.array(revisionContract),
        { signal },
      ),
  });
  const base = query.data?.spec;
  const current: Record<string, JsonValue> = draft ?? { ...(base ?? fresh) };
  const preview = useQuery({
    queryKey: ["data-preview", projectId, id, base?.version],
    enabled: false,
    retry: false,
    queryFn: ({ signal }) =>
      request(
        `/data-assets/${encodeURIComponent(id!)}/preview?version=${base!.version}`,
        previewContract,
        { signal },
      ),
  });
  function update(key: string, value: JsonValue) {
    setDraft({ ...current, [key]: value });
    setIssues([]);
  }
  async function saved(revision: z.infer<typeof revisionContract>) {
    client.setQueryData(
      ["data-workspace", projectId, revision.resource_id, 0],
      revision,
    );
    setDraft(null);
    setVersion(0);
    setIssues([]);
    navigate(`/data/${encodeURIComponent(revision.resource_id)}/workspace`, {
      replace: true,
    });
    await Promise.all([
      client.invalidateQueries({ queryKey: ["data"] }),
      client.invalidateQueries({ queryKey: ["data-history"] }),
    ]);
  }
  const save = useMutation({
    mutationFn: async () => {
      if (id && !base) throw new Error("数据版本尚未加载");
      let candidate: Record<string, unknown>;
      if (!id) {
        if (!file) throw new Error("请选择实际数据文件");
        if (file.size > 64 * 1024 * 1024)
          throw new Error("文件不得超过 64 MiB");
        const digest = await crypto.subtle.digest(
          "SHA-256",
          await file.arrayBuffer(),
        );
        const checksum = Array.from(new Uint8Array(digest), (byte) =>
          byte.toString(16).padStart(2, "0"),
        ).join("");
        candidate = {
          ...current,
          checksum,
          uri: "upload:pending",
          version: 1,
          quality: {},
        };
      } else candidate = { ...prepareDataRevision(current, base!) };
      const errors = contractErrors("DataAssetSpec", candidate);
      setIssues(errors);
      if (errors.length) throw new Error("请补全数据来源和科学字段");
      const spec = dataContract.parse(candidate);
      if (id)
        return request(
          `/data-assets/${encodeURIComponent(id)}`,
          revisionContract,
          { method: "PUT", body: { expected_version: base!.version, spec } },
        );
      const body = new FormData();
      body.append("project_id", projectId);
      body.append("metadata", JSON.stringify(spec));
      body.append("file", file!);
      return request("/data-assets/upload", revisionContract, {
        method: "POST",
        body,
      });
    },
    onSuccess: saved,
  });
  const validate = useMutation({
    mutationFn: () =>
      request(
        `/data-assets/${encodeURIComponent(id!)}/validate`,
        revisionContract,
        { method: "POST", body: { expected_version: base!.version } },
      ),
    onSuccess: saved,
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/data-assets/${encodeURIComponent(id!)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["data"] });
      navigate("/data");
    },
  });
  const busy = save.isPending || validate.isPending || archive.isPending;
  const historical = version !== 0;
  const variables = Array.isArray(current.variables) ? current.variables : [];
  if (id && query.isPending) return <Loading />;
  return (
    <>
      <Link to="/data">← 返回数据目录</Link>
      <PageTitle
        title={id ? "数据版本管理" : "上传数据"}
        description="来源和科学含义需要明确声明；文件结构、范围及质量由服务端实际读取检查。"
      />
      <ErrorNotice
        error={
          query.error ??
          history.error ??
          save.error ??
          validate.error ??
          archive.error ??
          preview.error
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
        <Panel title="版本与文件">
          <label>
            查看数据版本
            <select
              value={version}
              disabled={busy}
              onChange={(event) => {
                setVersion(Number(event.target.value));
                setDraft(null);
                setIssues([]);
              }}
            >
              <option value={0}>
                当前版本（{history.data?.at(-1)?.version ?? base.version}）
              </option>
              {history.data?.map((row) => (
                <option value={row.version} key={row.version}>
                  版本 {row.version}
                </option>
              ))}
            </select>
          </label>
          <p>
            当前显示版本 {base.version} ·{" "}
            <Status
              value={
                base.quality.validated === true ? "VALIDATED" : "UNVALIDATED"
              }
            />
          </p>
          <p className="break">文件 SHA-256：{base.checksum}</p>
          <a
            href={`/api/v1/data-assets/${encodeURIComponent(id)}/download?version=${base.version}`}
          >
            下载此版本原始文件
          </a>
          <div className="toolbar">
            <button
              disabled={busy || preview.isFetching}
              onClick={() => void preview.refetch()}
            >
              读取实际文件预览
            </button>
            <button
              disabled={busy || historical || draft !== null}
              onClick={() => validate.mutate()}
            >
              重新检查并保存质量版本
            </button>
            <button
              className="secondary"
              disabled={busy || historical || draft !== null}
              onClick={() => archive.mutate()}
            >
              归档数据
            </button>
          </div>
          <p>
            归档保留历史文件与血缘；被场景或运行引用的数据由服务端阻止归档。修改元数据后必须重新检查。
          </p>
        </Panel>
      ) : null}
      {!id || base ? (
        <Panel title="数据科学元数据">
          <fieldset disabled={busy || historical}>
            {!id ? (
              <label>
                数据文件
                <input
                  type="file"
                  accept=".tif,.tiff,.json,.geojson,.zip,.gpkg,.csv,.nc"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </label>
            ) : null}
            {(
              [
                ["name", "数据名称"],
                ["source", "数据来源"],
                ["license", "许可证"],
              ] as const
            ).map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  value={String(current[key] ?? "")}
                  onChange={(event) => update(key, event.target.value)}
                />
              </label>
            ))}
            <label>
              数据类别
              <select
                value={String(current.type)}
                onChange={(event) => update("type", event.target.value)}
              >
                {schema.$defs.DataAssetSpec.properties.type.enum
                  .filter((type) => !["service", "database"].includes(type))
                  .map((type) => (
                    <option key={type}>{type}</option>
                  ))}
              </select>
            </label>
            <label>
              文件格式
              <select
                value={String(current.format)}
                onChange={(event) => update("format", event.target.value)}
              >
                {schema.$defs.DataAssetSpec.properties.format.enum
                  .filter((format) => !["HTTP", "DATABASE"].includes(format))
                  .map((format) => (
                    <option key={format}>{format}</option>
                  ))}
              </select>
            </label>
            <p>
              未知坐标、范围或时期保持未设置；栅格和矢量必须与实际文件一致。上传最多
              64 MiB。Shapefile 使用包含配套文件的 ZIP。
            </p>
            <ScientificFields
              title="空间与时间声明"
              fixedFields
              values={Object.fromEntries(
                [
                  "crs",
                  "vertical_datum",
                  "spatial_extent",
                  "time_start",
                  "time_end",
                  "time_resolution",
                ].map((key) => [key, current[key] ?? null]),
              )}
              onChange={(next) => setDraft({ ...current, ...next })}
            />
            <ScientificFields
              title="变量定义"
              fixedFields
              options={modelFieldOptions}
              values={{ variables }}
              onChange={(next) => update("variables", next.variables!)}
            />
            <button
              className="secondary"
              onClick={() =>
                update("variables", [...variables, newDataVariable()])
              }
            >
              添加数据变量
            </button>
            <button disabled={busy || historical} onClick={() => save.mutate()}>
              {save.isPending
                ? "正在读取与保存…"
                : id
                  ? "保存数据修订"
                  : "上传并检查数据"}
            </button>
          </fieldset>
        </Panel>
      ) : null}
      {base ? (
        <Panel title="此版本质量记录">
          <Details title="测量记录与声明来源" value={base.quality} />
        </Panel>
      ) : null}
      {preview.data ? (
        <Panel title="实际文件预览">
          <p>
            预览为有界样本；质量检查覆盖服务端支持的结构与声明校验，不代表科学适用性已审批。
          </p>
          <Preview value={preview.data.preview} />
          <Details title="此次读取的测量记录" value={preview.data.metadata} />
        </Panel>
      ) : null}
    </>
  );
}
function Preview({ value }: { value: Record<string, JsonValue> }) {
  const rows = value.rows;
  if (
    Array.isArray(rows) &&
    rows.every(
      (row) => row !== null && typeof row === "object" && !Array.isArray(row),
    )
  ) {
    const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    return (
      <div className="table-scroll">
        <table aria-label="数据预览行">
          <thead>
            <tr>
              {columns.map((key) => (
                <th key={key}>{key}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((key) => (
                  <td key={key}>{JSON.stringify(row[key] ?? null)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <Details title="文件预览内容" value={value} />;
}
