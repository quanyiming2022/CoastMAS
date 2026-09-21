import { DataTable } from "./components";
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema, resourceSchema, jobSchema } from "./api";
import { contract, workflowContract } from "./contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle, Panel, Status } from "./components";
import WorkflowGraph from "./WorkflowGraph";
const recordContract = revisionSchema.extend({
  spec: contract("OptimizationSpec"),
});
const validationContract = z.object({
  valid: z.boolean(),
  issues: z.array(z.object({ code: z.string(), message: z.string() })),
});
const runsContract = z.array(
  z.object({ job: jobSchema, result_id: z.string().nullable() }),
);
const outputContract = z.object({
  outputs: z.object({ "optimize.allocation": contract("OptimizationOutcome") }),
  result_view: z.object({ binding_status: z.string() }),
});

export default function SpatialOptimization() {
  const { projectId } = useWorkspace();
  return <List key={projectId} projectId={projectId} />;
}
function List({ projectId }: { projectId: string }) {
  const [page, setPage] = useState(0);
  const records = useQuery({
    queryKey: ["optimizations", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/optimizations?project_id=${projectId}&limit=50&offset=${page * 50}`,
        z.array(recordContract),
        { signal },
      ),
  });
  return (
    <>
      <PageTitle
        title="空间优化"
        description="在预算、面积、生态成本、可加风险指标和保护约束下，计算候选单元分配。结果辅助研究，系统不自动作出政策决定。"
        actions={
          <Link className="button" to="/optimizations/new">
            新建优化配置
          </Link>
        }
      />
      <ErrorNotice error={records.error} />
      <Panel title="固定优化配置">
        {records.isPending ? (
          <Loading />
        ) : (
          <DataTable>
            <thead>
              <tr>
                <th>名称</th>
                <th className="numeric">版本</th>
                <th className="table-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              {records.data?.map((row) => (
                <tr key={row.resource_id}>
                  <td>{row.spec.name}</td>
                  <td className="numeric">v{row.version}</td>
                  <td className="table-actions">
                    <Link
                      to={`/optimizations/${encodeURIComponent(row.resource_id)}`}
                    >
                      查看与运行
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        )}
        {!records.isPending && !records.error && !records.data?.length ? (
          <p className="empty">暂无优化配置。</p>
        ) : null}
        <div className="pagination">
          <button
            className="secondary"
            disabled={page === 0}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span>第 {page + 1} 页</span>
          <button
            className="secondary"
            disabled={(records.data?.length ?? 0) < 50}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      </Panel>
    </>
  );
}
const numericFields = [
  ["budget", "预算上限"],
  ["minimum_area", "最低面积"],
  ["maximum_ecological_cost", "生态成本上限"],
  ["maximum_risk", "风险指标上限"],
] as const;
const unitFields = [
  ["area_unit", "面积单位"],
  ["benefit_unit", "收益单位"],
  ["cost_unit", "成本单位"],
  ["ecological_cost_unit", "生态成本单位"],
  ["risk_unit", "风险单位"],
] as const;
const candidateFields = [
  ["id", "候选标识"],
  ["benefit", "候选收益"],
  ["cost", "候选成本"],
  ["area", "候选面积"],
  ["ecological_cost", "候选生态成本"],
  ["risk", "候选风险"],
] as const;
type CandidateDraft = {
  key: string;
  id: string;
  benefit: string;
  cost: string;
  area: string;
  ecological_cost: string;
  risk: string;
  allowed: boolean;
};
const emptyCandidate = (): CandidateDraft => ({
  key: crypto.randomUUID(),
  id: "",
  benefit: "",
  cost: "",
  area: "",
  ecological_cost: "",
  risk: "",
  allowed: false,
});
const number = (value: string) => (value.trim() === "" ? NaN : Number(value));
export function OptimizationEditor() {
  const { projectId } = useWorkspace();
  return <Editor key={projectId} projectId={projectId} />;
}
function Editor({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [selected, setSelected] = useState("");
  const [scenePage, setScenePage] = useState(0);
  const [units, setUnits] = useState<CandidateDraft[]>([]);
  const [bounds, setBounds] = useState({
    budget: "",
    minimum_area: "",
    maximum_ecological_cost: "",
    maximum_risk: "",
  });
  const [labels, setLabels] = useState({
    area_unit: "",
    benefit_unit: "",
    cost_unit: "",
    ecological_cost_unit: "",
    risk_unit: "",
  });
  const [basis, setBasis] = useState("");
  const [dataLabel, setDataLabel] = useState("");
  const [timeLimit, setTimeLimit] = useState("30");
  const [key] = useState(() => crypto.randomUUID());
  const scenes = useQuery({
    queryKey: ["optimization-scenes", projectId, scenePage],
    queryFn: ({ signal }) =>
      request(
        `/scenes?project_id=${projectId}&limit=50&offset=${scenePage * 50}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const save = useMutation({
    mutationFn: () => {
      const scene = z
        .tuple([z.string(), z.number()])
        .parse(JSON.parse(selected));
      const frame = contract("OptimizationFrame").parse({
        ...labels,
        ...Object.fromEntries(
          numericFields.map(([field]) => [field, number(bounds[field])]),
        ),
        units: units.map((item) => ({
          id: item.id,
          benefit: number(item.benefit),
          cost: number(item.cost),
          area: number(item.area),
          ecological_cost: number(item.ecological_cost),
          risk: number(item.risk),
          allowed: item.allowed,
        })),
        protected_unit_ids: [],
        risk_aggregation: "additive_index",
        additivity_basis: basis,
        data_label: dataLabel,
      });
      return request("/optimizations", recordContract, {
        method: "POST",
        body: {
          project_id: projectId,
          name,
          scene: { id: scene[0], version: scene[1] },
          frame,
          time_limit: number(timeLimit),
          idempotency_key: key,
        },
      });
    },
    onSuccess: (result) =>
      navigate(`/optimizations/${encodeURIComponent(result.resource_id)}`),
  });
  const example = () => {
    setName("SYNTHETIC spatial optimization");
    setLabels({
      area_unit: "ha",
      benefit_unit: "1",
      cost_unit: "1",
      ecological_cost_unit: "1",
      risk_unit: "1",
    });
    setBounds({
      budget: "3",
      minimum_area: "1",
      maximum_ecological_cost: "2",
      maximum_risk: "2",
    });
    setBasis(
      "SYNTHETIC additive benefit and cost indices; risk is an additive penalty, not probability. Candidate areas are declared non-overlapping areas.",
    );
    setDataLabel("SYNTHETIC");
    setUnits([
      {
        ...emptyCandidate(),
        id: "protected",
        benefit: "1000000",
        cost: "1",
        area: "1",
        ecological_cost: "0",
        risk: "0",
        allowed: false,
      },
      {
        ...emptyCandidate(),
        id: "a",
        benefit: "5",
        cost: "2",
        area: "1",
        ecological_cost: "1",
        risk: "1",
        allowed: true,
      },
      {
        ...emptyCandidate(),
        id: "b",
        benefit: "8",
        cost: "3",
        area: "2",
        ecological_cost: "1",
        risk: "1",
        allowed: true,
      },
    ]);
  };
  return (
    <>
      <Link to="/optimizations">← 返回空间优化</Link>
      <PageTitle
        title="新建优化配置"
        description="保存实际输入文件和独立固定场景，不覆盖基础场景。所有数值与单位均需明确，示范数据只用于验证。"
      />
      <Panel title="配置与假设">
        <button type="button" onClick={example}>
          载入合成示范
        </button>
        <form
          className="form-workspace form-stack"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate();
          }}
        >
          <ErrorNotice error={save.error ?? scenes.error} />
          <label>
            优化名称
            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            基础场景
            <select
              required
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">选择固定场景版本</option>
              {scenes.data?.map((item) => (
                <option
                  key={item.id}
                  value={JSON.stringify([item.id, item.version])}
                >
                  {item.name} · v{item.version}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            type="button"
            disabled={scenePage === 0}
            onClick={() => setScenePage(scenePage - 1)}
          >
            上一页场景
          </button>
          <button
            className="secondary"
            type="button"
            disabled={(scenes.data?.length ?? 0) < 50}
            onClick={() => setScenePage(scenePage + 1)}
          >
            下一页场景
          </button>
          <label>
            数据来源标记
            <input
              required
              value={dataLabel}
              onChange={(event) => setDataLabel(event.target.value)}
            />
          </label>
          <label>
            可加性与科学依据
            <textarea
              required
              value={basis}
              onChange={(event) => setBasis(event.target.value)}
            />
          </label>
          <p>
            收益、成本和风险按列相加；风险为可加惩罚指标，不将概率直接相加。面积应代表互不重叠的候选单元。标准单位可填
            m^2、ha、1；无量纲指标须在依据中说明定义。
          </p>
          <div className="form-grid">
            {unitFields.map(([field, label]) => (
              <label key={field}>
                {label}
                <input
                  required
                  value={labels[field]}
                  onChange={(event) =>
                    setLabels({ ...labels, [field]: event.target.value })
                  }
                />
              </label>
            ))}
            {numericFields.map(([field, label]) => (
              <label key={field}>
                {label}
                <input
                  required
                  type="number"
                  step="any"
                  min="0"
                  value={bounds[field]}
                  onChange={(event) =>
                    setBounds({ ...bounds, [field]: event.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <label>
            计算时限（秒）
            <input
              required
              type="number"
              step="any"
              min="0.01"
              max="120"
              value={timeLimit}
              onChange={(event) => setTimeLimit(event.target.value)}
            />
          </label>
          <h3>候选单元</h3>
          <p>
            标识与所选场景的管理单元标识一致才能绑定地图。未绑定时保留数表并明确标记，不能假称具有空间定位。取消「允许选择」是硬保护，任何收益都不能覆盖；基础场景中的保护清单也会保留。
          </p>
          {units.map((item, index) => (
            <fieldset key={item.key}>
              <legend>候选单元 {index + 1}</legend>
              <div className="form-grid">
                {candidateFields.map(([field, label]) => (
                  <label key={field}>
                    {label} {index + 1}
                    <input
                      required
                      type={field === "id" ? "text" : "number"}
                      step="any"
                      value={item[field]}
                      onChange={(event) =>
                        setUnits(
                          units.map((value, i) =>
                            i === index
                              ? { ...value, [field]: event.target.value }
                              : value,
                          ),
                        )
                      }
                    />
                  </label>
                ))}
              </div>
              <label>
                <input
                  type="checkbox"
                  checked={item.allowed}
                  onChange={(event) =>
                    setUnits(
                      units.map((value, i) =>
                        i === index
                          ? { ...value, allowed: event.target.checked }
                          : value,
                      ),
                    )
                  }
                />
                允许选择 {index + 1}
              </label>
              <button
                className="danger"
                type="button"
                onClick={() => setUnits(units.filter((_, i) => i !== index))}
              >
                删除候选 {index + 1}
              </button>
            </fieldset>
          ))}
          <button
            className="secondary"
            type="button"
            disabled={units.length >= 5000}
            onClick={() => setUnits([...units, emptyCandidate()])}
          >
            添加候选单元
          </button>
          <button type="submit" disabled={save.isPending || units.length === 0}>
            保存固定优化配置
          </button>
        </form>
      </Panel>
    </>
  );
}
export function OptimizationRecord() {
  const { id = "" } = useParams();
  const { projectId } = useWorkspace();
  return <Record key={`${projectId}:${id}`} id={id} projectId={projectId} />;
}
function Record({ id, projectId }: { id: string; projectId: string }) {
  const navigate = useNavigate();
  const [seed, setSeed] = useState(42);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [page, setPage] = useState(0);
  const [selectedResult, setSelectedResult] = useState("");
  const path = `/optimizations/${encodeURIComponent(id)}`;
  const record = useQuery({
    queryKey: ["optimization-record", projectId, id],
    queryFn: ({ signal }) => request(path, recordContract, { signal }),
  });
  const spec = record.data?.spec;
  const input = useQuery({
    queryKey: ["optimization-input", projectId, id],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(path + "/input", contract("OptimizationFrame"), { signal }),
  });
  const workflow = useQuery({
    queryKey: ["optimization-workflow", projectId, spec?.workflow.id],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(
        `/workflows/${encodeURIComponent(spec!.workflow.id)}?version=${spec!.workflow.version}`,
        revisionSchema.extend({ spec: workflowContract }),
        { signal },
      ),
  });
  const runs = useQuery({
    queryKey: ["optimization-runs", projectId, id, page],
    enabled: !!spec,
    queryFn: ({ signal }) =>
      request(`${path}/runs?limit=50&offset=${page * 50}`, runsContract, {
        signal,
      }),
    refetchInterval: (query) =>
      query.state.data?.some((row) =>
        ["QUEUED", "RUNNING"].includes(row.job.status),
      )
        ? 2000
        : false,
  });
  const resultId =
    selectedResult || runs.data?.find((row) => row.result_id)?.result_id;
  const output = useQuery({
    queryKey: ["optimization-output", projectId, resultId],
    enabled: !!resultId,
    queryFn: ({ signal }) =>
      request(
        `/results/${encodeURIComponent(resultId!)}/content`,
        outputContract,
        { signal },
      ),
  });
  const validate = useMutation({
    mutationFn: () =>
      request(
        `/workflows/${encodeURIComponent(spec!.workflow.id)}/validate`,
        validationContract,
        {
          method: "POST",
          body: {
            workflow_version: spec!.workflow.version,
            scene_id: spec!.scene.id,
            scene_version: spec!.scene.version,
            random_seed: seed,
          },
        },
      ),
  });
  const run = useMutation({
    mutationFn: () =>
      request(path + "/run", jobSchema, {
        method: "POST",
        body: { optimization_version: spec!.version, random_seed: seed },
        idempotencyKey: key,
      }),
    onSuccess: (job) => navigate(`/runs/${encodeURIComponent(job.id)}`),
  });
  const archive = useMutation({
    mutationFn: () => request(path, z.null(), { method: "DELETE" }),
    onSuccess: () => navigate("/optimizations"),
  });
  const outcome = output.data?.outputs["optimize.allocation"];
  return (
    <>
      <Link to="/optimizations">← 返回空间优化</Link>
      <PageTitle
        title="优化配置与结果"
        description="固定输入、模型、场景和工作流版本。计算成功不等于存在可行方案；优化结果不替代真实政策决定。"
      />
      <ErrorNotice
        error={
          record.error ??
          input.error ??
          workflow.error ??
          runs.error ??
          output.error ??
          validate.error ??
          run.error ??
          archive.error
        }
      />
      {record.isPending ? (
        <Loading />
      ) : spec ? (
        <>
          <Panel title={spec.name}>
            <p>
              记录 v{spec.version} · 输入版本 v{spec.data.version} · 固定场景 v
              {spec.scene.version}
            </p>
            <Link
              to={`/data/${encodeURIComponent(spec.data.id)}?version=${spec.data.version}`}
            >
              查看固定输入文件
            </Link>
            <p>
              <a
                href={`/api/v1/scenes/${encodeURIComponent(spec.scene.id)}?version=${spec.scene.version}`}
                target="_blank"
                rel="noreferrer"
              >
                查看固定场景原文
              </a>
            </p>
            {input.data ? (
              <>
                <p>数据标记：{input.data.data_label}</p>
                <p>{input.data.additivity_basis}</p>
                <p>
                  预算 ≤ {input.data.budget} {input.data.cost_unit}；面积 ≥{" "}
                  {input.data.minimum_area} {input.data.area_unit}；生态成本 ≤{" "}
                  {input.data.maximum_ecological_cost}{" "}
                  {input.data.ecological_cost_unit}；风险 ≤{" "}
                  {input.data.maximum_risk} {input.data.risk_unit}。
                </p>
              </>
            ) : null}
            <label>
              随机种子
              <input
                type="number"
                min="0"
                max="4294967295"
                value={seed}
                onChange={(event) => {
                  setSeed(Number(event.target.value));
                  setKey(crypto.randomUUID());
                  validate.reset();
                }}
              />
            </label>
            <button
              disabled={validate.isPending}
              onClick={() => validate.mutate()}
            >
              科学预检
            </button>
            <button
              disabled={!validate.data?.valid || run.isPending}
              onClick={() => run.mutate()}
            >
              提交优化运行
            </button>
            <button
              className="danger"
              disabled={archive.isPending}
              onClick={() => archive.mutate()}
            >
              归档配置
            </button>
            {validate.data ? (
              <>
                <p>{validate.data.valid ? "科学预检通过" : "科学预检未通过"}</p>
                {validate.data.issues.map((issue, index) => (
                  <p key={index}>
                    {issue.code}：{issue.message}
                  </p>
                ))}
              </>
            ) : null}
            {workflow.data ? (
              <WorkflowGraph workflow={workflow.data.spec} />
            ) : null}
          </Panel>
          <Panel title="真实运行记录">
            <DataTable>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>运行状态</th>
                  <th className="table-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                {runs.data?.map((row) => (
                  <tr key={row.job.id}>
                    <td>
                      <Link to={`/runs/${encodeURIComponent(row.job.id)}`}>
                        {row.job.id}
                      </Link>
                    </td>
                    <td>
                      <Status value={row.job.status} />
                    </td>
                    <td className="table-actions">
                      {row.result_id ? (
                        <>
                          <button
                            className="secondary"
                            onClick={() => setSelectedResult(row.result_id!)}
                          >
                            查看优化结果
                          </button>
                          <Link
                            to={`/results/${encodeURIComponent(row.result_id)}`}
                          >
                            地图与完整结果
                          </Link>
                        </>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
            {runs.isPending ? (
              <Loading />
            ) : !runs.error && !runs.data?.length ? (
              <p className="empty">暂无运行记录。</p>
            ) : null}
            <div className="pagination">
              <button
                className="secondary"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                上一页运行
              </button>
              <button
                className="secondary"
                disabled={(runs.data?.length ?? 0) < 50}
                onClick={() => setPage(page + 1)}
              >
                下一页运行
              </button>
            </div>
          </Panel>
          {outcome ? (
            <Panel title="实际优化结果">
              <p>优化状态：{outcome.status}</p>
              <p>空间绑定：{output.data!.result_view.binding_status}</p>
              <p>{outcome.solver_message}</p>
              {outcome.status === "INCUMBENT" ? (
                <p>
                  当前仅有可行候选，未证明最优。相对间隙：
                  {outcome.relative_gap ?? "未报告"}
                </p>
              ) : null}
              {!outcome.constraints_satisfied ? (
                <p>没有可行分配，不把空结果解释为全部未选中。</p>
              ) : (
                <p>经核验的分配满足硬约束；面积统一以平方米报告。</p>
              )}
              {outcome.totals ? (
                <p>
                  总收益：{outcome.totals.benefit} {outcome.benefit_unit} ·
                  总成本：{outcome.totals.cost} {outcome.cost_unit} · 总面积：
                  {outcome.totals.area} m²
                </p>
              ) : null}
              <DataTable>
                <thead>
                  <tr>
                    <th>硬约束</th>
                    <th>方向</th>
                    <th className="numeric">边界</th>
                    <th className="numeric">实际值</th>
                    <th>单位</th>
                    <th>核验</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(outcome.checks).map(([name, check]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{check.relation === "le" ? "≤" : "≥"}</td>
                      <td className="numeric">{check.bound}</td>
                      <td className="numeric">{check.actual ?? "无可行值"}</td>
                      <td>{check.unit}</td>
                      <td>
                        {check.satisfied === null
                          ? "未获得可行解"
                          : check.satisfied
                            ? "满足"
                            : "不满足"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
              <DataTable>
                <thead>
                  <tr>
                    <th>候选标识</th>
                    <th>硬保护</th>
                    <th className="numeric">分配</th>
                    <th className="numeric">面积 m²</th>
                    <th className="numeric">收益</th>
                    <th className="numeric">成本</th>
                  </tr>
                </thead>
                <tbody>
                  {outcome.allocations.map((item) => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td>{item.allowed ? "允许" : "禁止"}</td>
                      <td className="numeric">
                        {item.selected === null
                          ? "无分配"
                          : item.selected
                            ? "选中"
                            : "未选"}
                      </td>
                      <td className="numeric">{item.area}</td>
                      <td className="numeric">{item.benefit}</td>
                      <td className="numeric">{item.cost}</td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </Panel>
          ) : null}
        </>
      ) : null}
    </>
  );
}
