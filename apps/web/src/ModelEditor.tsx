import { useMemo, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema, userSchema } from "./api";
import { contractErrors, modelContract } from "./contracts";
import { useWorkspace } from "./workspace";
import {
  freshModel,
  prepareModelRevision,
  modelFieldOptions,
  modelTypes,
} from "./model-editor";
import { ErrorNotice, Loading, PageTitle, Panel, Status } from "./components";
import ScientificFields from "./ScientificFields";

const modelRevision = revisionSchema.extend({ spec: modelContract });

const runtimes = [
  "metadata",
  "python",
  "cli",
  "docker",
  "http",
  "raster_gis",
  "ml",
];
const variableTemplate = {
  name: "",
  standard_name: "",
  description: "",
  data_type: null,
  unit: "",
  dimension: "",
  semantic_type: null,
  spatial_support: "",
  temporal_support: "",
  aggregation_type: null,
  nodata_policy: null,
  required: true,
};
const editableGroups = [
  ["输入输出与参数", ["inputs", "outputs", "parameters"]],
  [
    "科学适用范围",
    [
      "spatial_scale",
      "temporal_scale",
      "supported_geometry",
      "supported_crs",
      "constraints",
    ],
  ],
  ["运行配置与文献", ["runtime_config", "references"]],
] as const;
function items(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function text(value: unknown) {
  return typeof value === "string" ? value : "";
}
function tags(value: unknown) {
  return Array.isArray(value)
    ? value
        .filter((item): item is string => typeof item === "string")
        .join(", ")
    : "";
}

export default function ModelEditor() {
  const { id } = useParams();
  const { projectId } = useWorkspace();
  return (
    <Editor key={`${projectId}:${id ?? "new"}`} id={id} projectId={projectId} />
  );
}
function Editor({
  id,
  projectId,
}: {
  id: string | undefined;
  projectId: string;
}) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState<Record<string, unknown> | null>(null);
  const [localError, setLocalError] = useState<unknown>(null);
  const [copyName, setCopyName] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const user = useQuery({
    queryKey: ["current-user"],
    queryFn: ({ signal }) => request("/auth/me", userSchema, { signal }),
  });
  const fresh = useMemo(
    () => freshModel(user.data?.user_id ?? "", new Date().toISOString()),
    [user.data?.user_id],
  );
  const key = ["model-editor", projectId, id, version];
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) =>
      request(
        `/models/${encodeURIComponent(id!)}${version ? `?version=${version}` : ""}`,
        modelRevision,
        { signal },
      ),
    enabled: !!id,
  });
  const history = useQuery({
    queryKey: ["model-history", projectId, id],
    queryFn: ({ signal }) =>
      request(
        `/models/${encodeURIComponent(id!)}/versions`,
        z.array(modelRevision),
        { signal },
      ),
    enabled: !!id,
  });
  const base = query.data?.spec ?? null;
  const current: Record<string, unknown> = draft ?? { ...(base ?? fresh) };
  const historical = version !== 0;
  const dirty = draft !== null;
  function update(name: string, value: unknown) {
    setDraft({ ...current, [name]: value });
    setErrors([]);
  }
  async function saved(revision: z.infer<typeof modelRevision>) {
    client.setQueryData(
      ["model-editor", projectId, revision.resource_id, 0],
      revision,
    );
    setDraft(null);
    setVersion(0);
    setErrors([]);
    navigate(`/models/${encodeURIComponent(revision.resource_id)}/edit`, {
      replace: true,
    });
    await Promise.all([
      client.invalidateQueries({ queryKey: ["models"] }),
      client.invalidateQueries({ queryKey: ["model-history"] }),
    ]);
  }
  const save = useMutation({
    mutationFn: async () => {
      const candidate = {
        ...current,
        validation_status: "UNVALIDATED",
        execution_status: "NOT_EXECUTABLE",
      };
      const issues = contractErrors("ModelSpec", candidate);
      setErrors(issues);
      if (issues.length) throw new Error("请修正下方标出的模型字段");
      const spec = prepareModelRevision(
        current,
        base,
        new Date().toISOString(),
      );
      return request(
        id ? `/models/${encodeURIComponent(id)}` : "/models",
        modelRevision,
        {
          method: id ? "PUT" : "POST",
          body: id
            ? { expected_version: base!.version, spec }
            : { project_id: projectId, spec },
        },
      );
    },
    onSuccess: saved,
  });
  const lifecycle = useMutation({
    mutationFn: async (action: "toggle" | "copy") => {
      if (!base || !id) throw new Error("尚未加载模型版本");
      return request(
        `/models/${encodeURIComponent(id)}/${action === "copy" ? "copy" : "enabled"}`,
        modelRevision,
        {
          method: "POST",
          body:
            action === "copy"
              ? { name: copyName.trim() }
              : { expected_version: base.version, enabled: !base.enabled },
        },
      );
    },
    onSuccess: saved,
  });
  const archive = useMutation({
    mutationFn: () =>
      request(`/models/${encodeURIComponent(id!)}`, z.null(), {
        method: "DELETE",
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["models"] });
      navigate("/models");
    },
  });
  const importer = useMutation({
    mutationFn: async (file: File) => {
      if (file.size > 262144) throw new Error("模型文件不得超过256 KiB");
      const format = /\.ya?ml$/i.test(file.name) ? "yaml" : "json";
      return request("/models/import", modelRevision, {
        method: "POST",
        body: {
          project_id: projectId,
          format,
          content: await file.text(),
          identifier: `model:${crypto.randomUUID()}`,
        },
      });
    },
    onSuccess: saved,
  });
  function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) importer.mutate(file);
    event.target.value = "";
  }
  const busy =
    save.isPending ||
    lifecycle.isPending ||
    archive.isPending ||
    importer.isPending;
  if (user.isPending || (id && query.isPending)) return <Loading />;
  if (user.error || query.error)
    return <ErrorNotice error={user.error ?? query.error} />;
  return (
    <>
      <Link to="/models">← 返回模型中心</Link>
      <PageTitle
        title={id ? "模型版本管理" : "新增模型"}
        description="科学契约修改后需要重新验证；登记元数据不会自动获得执行资格。"
      />
      {[
        localError,
        save.error,
        lifecycle.error,
        archive.error,
        importer.error,
        history.error,
      ].map((error, index) => (
        <ErrorNotice key={index} error={error} />
      ))}
      {errors.length ? (
        <ul role="alert">
          {errors.map((error, index) => (
            <li key={index}>{error}</li>
          ))}
        </ul>
      ) : null}
      <Panel title="模型文件与版本">
        <label>
          导入 JSON / YAML 模型文件
          <input
            type="file"
            accept=".json,.yaml,.yml"
            disabled={busy}
            onChange={upload}
          />
        </label>
        {base && id ? (
          <>
            <Status value={base.validation_status} />
            <Status value={base.execution_status ?? "NOT_EXECUTABLE"} />
            <label>
              查看模型版本
              <select
                value={version}
                onChange={(event) => {
                  setDraft(null);
                  setVersion(Number(event.target.value));
                  setErrors([]);
                }}
              >
                <option value={0}>
                  当前最新版本 v{history.data?.at(-1)?.version ?? base.version}
                </option>
                {history.data?.map((item) => (
                  <option key={item.version} value={item.version}>
                    历史 v{item.version}
                  </option>
                ))}
              </select>
            </label>
            <a
              className="button secondary"
              href={`/api/v1/models/${encodeURIComponent(id)}/export?format=json&version=${base.version}`}
              download
            >
              导出此版本 JSON
            </a>
            <a
              className="button secondary"
              href={`/api/v1/models/${encodeURIComponent(id)}/export?format=yaml&version=${base.version}`}
              download
            >
              导出此版本 YAML
            </a>
            <label>
              复制模型名称
              <input
                value={copyName}
                onChange={(event) => setCopyName(event.target.value)}
              />
            </label>
            <button
              disabled={busy || historical || !copyName.trim()}
              onClick={() => lifecycle.mutate("copy")}
            >
              复制最新模型
            </button>
            <button
              className="secondary"
              disabled={busy || historical || dirty}
              onClick={() => lifecycle.mutate("toggle")}
            >
              {base.enabled ? "停用模型" : "启用模型"}
            </button>
            <button
              className="secondary"
              disabled={busy || historical || dirty}
              onClick={() => archive.mutate()}
            >
              归档模型
            </button>
          </>
        ) : null}
        {historical ? (
          <p>正在查看不可变历史版本。选择当前最新版本后编辑。</p>
        ) : null}
      </Panel>
      <fieldset disabled={historical || busy}>
        <legend>模型科学契约</legend>
        <label>
          模型名称
          <input
            value={text(current.name)}
            onChange={(event) => update("name", event.target.value)}
          />
        </label>
        <label>
          展示名称
          <input
            value={text(current.display_name)}
            onChange={(event) => update("display_name", event.target.value)}
          />
        </label>
        <label>
          说明
          <textarea
            value={text(current.description)}
            onChange={(event) => update("description", event.target.value)}
          />
        </label>
        <label>
          模型类型
          <select
            value={text(current.model_type)}
            onChange={(event) => update("model_type", event.target.value)}
          >
            {modelTypes.map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
        </label>
        <label>
          运行类型
          <select
            value={text(current.runtime_type)}
            onChange={(event) => update("runtime_type", event.target.value)}
          >
            {runtimes.map((runtime) => (
              <option key={runtime} value={runtime}>
                {runtime === "metadata" ? "仅元数据（不执行）" : runtime}
              </option>
            ))}
          </select>
        </label>
        <label>
          许可证
          <input
            value={text(current.license)}
            onChange={(event) => update("license", event.target.value)}
          />
        </label>
        {[
          ["capabilities", "能力（逗号分隔）"],
          ["scientific_domain", "科学领域（逗号分隔）"],
        ].map(([field, label]) => (
          <label key={field}>
            {label}
            <input
              value={tags(current[field!])}
              onChange={(event) =>
                update(
                  field!,
                  event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                )
              }
            />
          </label>
        ))}
        <div className="toolbar">
          {[
            ["inputs", "添加输入变量"],
            ["outputs", "添加输出变量"],
          ].map(([field, label]) => (
            <button
              key={field}
              className="secondary"
              onClick={() =>
                update(field!, [
                  ...items(current[field!]),
                  structuredClone(variableTemplate),
                ])
              }
            >
              {label}
            </button>
          ))}
          <button
            className="secondary"
            onClick={() =>
              update("parameters", [
                ...(Array.isArray(current.parameters)
                  ? current.parameters
                  : []),
                {
                  name: "",
                  unit: "",
                  minimum: null,
                  maximum: null,
                  default: null,
                  required: true,
                },
              ])
            }
          >
            添加参数
          </button>
        </div>
        {editableGroups.map(([title, fields]) => (
          <ScientificFields
            key={title}
            title={title}
            fixedFields
            options={modelFieldOptions}
            values={Object.fromEntries(
              fields.map((field) => [field, current[field]]),
            )}
            onChange={(values) => {
              setDraft({ ...current, ...values });
              setErrors([]);
            }}
          />
        ))}
        <button
          disabled={busy || !user.data}
          onClick={() => {
            setLocalError(null);
            save.mutate();
          }}
        >
          保存模型版本
        </button>
      </fieldset>
    </>
  );
}
