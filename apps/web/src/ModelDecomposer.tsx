import { DataTable } from "./components";
import { useRef, useState, type ChangeEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { z } from "zod";
import { request } from "./api";
import { contract } from "./contracts";
import { ErrorNotice, PageTitle, Panel } from "./components";
import { decompositionGraph, stageLabels } from "./decomposition-graph";
import type {
  DecompositionRequest,
  ModelDecomposition,
} from "./generated/contracts";
const requestContract = contract("DecompositionRequest");
const responseContract = contract("ModelDecomposition");
const modes = {
  python: "Python 源文件",
  cli: "命令行参数",
  declared: "已声明组件",
  pipeline: "已有流程",
  black_box: "黑箱原子模型",
} as const;

export default function ModelDecomposer() {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<DecompositionRequest["kind"]>("python");
  const [source, setSource] = useState("");
  const [document, setDocument] = useState<Record<string, unknown>>({
    components: [],
    dependencies: [],
  });
  const [argv, setArgv] = useState("");
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const uploadSequence = useRef(0);
  const [artifact, setArtifact] = useState<{
    signature: string;
    result: ModelDecomposition;
  } | null>(null);
  const body = {
    ...(kind === "python"
      ? { source }
      : kind === "cli"
        ? { argv: argv.split("\n").filter((line) => line.trim() !== "") }
        : kind === "black_box"
          ? {}
          : document),
    name: name.trim(),
    kind,
  };
  const signature = JSON.stringify(body);
  const result = artifact?.signature === signature ? artifact.result : null;
  const mutation = useMutation({
    mutationFn: (submitted: DecompositionRequest) =>
      request("/models/decompose", responseContract, {
        method: "POST",
        body: submitted,
      }),
    onSuccess: (result, submitted) =>
      setArtifact({ signature: JSON.stringify(submitted), result }),
  });
  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const sequence = ++uploadSequence.current;
    try {
      if (file.size > 262144) throw new Error("源文件不得超过256 KiB");
      const content = await file.text();
      if (sequence !== uploadSequence.current) return;
      if (kind === "python") setSource(content);
      else
        setDocument(
          z.record(z.string(), z.unknown()).parse(JSON.parse(content)),
        );
      setFileName(file.name);
      setError(null);
    } catch (failure) {
      if (sequence === uploadSequence.current) setError(failure);
    }
  }
  function submit() {
    try {
      setError(null);
      mutation.mutate(requestContract.parse(body));
    } catch (failure) {
      setError(failure);
    }
  }
  function download() {
    if (!result) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }),
    );
    const anchor = window.document.createElement("a");
    anchor.href = url;
    anchor.download = "coastmas-decomposition.json";
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  return (
    <>
      <Link to="/models">← 返回模型中心</Link>
      <PageTitle
        title="模型静态拆解"
        description="静态分析源文件或声明结构；不会导入或执行上传代码。"
      />
      <ErrorNotice error={error ?? mutation.error} />
      <Panel title="拆解输入">
        <label>
          待拆解模型名称
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          拆解方式
          <select
            value={kind}
            onChange={(event) => {
              uploadSequence.current++;
              setKind(event.target.value as DecompositionRequest["kind"]);
              setError(null);
            }}
          >
            {Object.entries(modes).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {kind === "python" || kind === "declared" || kind === "pipeline" ? (
          <label>
            {kind === "python" ? "上传 Python 源文件" : "上传组件与依赖 JSON"}
            <input
              type="file"
              accept={kind === "python" ? ".py" : ".json"}
              onChange={(event) => void upload(event)}
            />
          </label>
        ) : null}
        {fileName ? <p>已读取：{fileName}</p> : null}
        {kind === "python" ? (
          <label>
            待分析的 Python 源码
            <textarea
              rows={12}
              value={source}
              onChange={(event) => {
                uploadSequence.current++;
                setSource(event.target.value);
              }}
            />
          </label>
        ) : null}
        {kind === "cli" ? (
          <label>
            完整命令行参数（每行一个参数，空行忽略；首行为程序名）
            <textarea
              rows={8}
              value={argv}
              onChange={(event) => setArgv(event.target.value)}
            />
          </label>
        ) : null}
        {kind === "declared" || kind === "pipeline" ? (
          <p>
            JSON 文件包含 components 和
            dependencies；组件声明预处理、计算、后处理或验证阶段，以及输入输出。依赖必须无环且引用已声明组件。
          </p>
        ) : null}
        {kind === "black_box" ? (
          <p>保留完整模型为一个原子组件，不推断或改写内部科学机制。</p>
        ) : null}
        <button disabled={mutation.isPending || !name.trim()} onClick={submit}>
          {mutation.isPending ? "正在静态分析…" : "生成拆解候选"}
        </button>
        {artifact && !result ? (
          <p>输入已变更，旧候选已隐藏，请重新生成。</p>
        ) : null}
      </Panel>
      {result ? (
        <DecompositionResult result={result} download={download} />
      ) : null}
    </>
  );
}
function DecompositionResult({
  result,
  download,
}: {
  result: ModelDecomposition;
  download: () => void;
}) {
  const graph = decompositionGraph(result);
  return (
    <Panel title="待审核拆解候选">
      <p>候选需要人工检查和科学验证，尚不可执行。</p>
      <p>
        {result.mode === "BLACK_BOX"
          ? "黑箱：保持原子模型"
          : "白箱：展示静态组件依赖"}
      </p>
      {result.warnings?.length ? (
        <ul>
          {result.warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      ) : null}
      <div className="workflow-graph" aria-label="模型拆解依赖图">
        <ReactFlow
          nodes={graph.nodes}
          edges={graph.edges}
          nodesDraggable={false}
          nodesConnectable={false}
          fitView
          minZoom={0.1}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>

      <DataTable aria-label="拆解组件">
        <thead>
          <tr>
            <th>组件</th>
            <th>阶段</th>
            <th>输入</th>
            <th>输出</th>
            <th>保留原子性</th>
          </tr>
        </thead>
        <tbody>
          {result.components.map((component) => (
            <tr key={component.id}>
              <td>
                {component.id}
                <small className="break">{component.signature}</small>
              </td>
              <td>{stageLabels[component.stage]}</td>
              <td>{component.inputs?.join("、") || "未声明"}</td>
              <td>{component.outputs?.join("、") || "未声明"}</td>
              <td>{component.atomic ? "是" : "否"}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>

      {Object.keys(result.cli_arguments ?? {}).length ? (
        <dl className="definition-grid">
          {Object.entries(result.cli_arguments ?? {}).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <button className="secondary" onClick={download}>
        下载拆解候选
      </button>
    </Panel>
  );
}
