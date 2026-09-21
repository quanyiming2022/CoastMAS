import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";
import { request, revisionSchema } from "./api";
import { contract } from "./contracts";
import type { CoastMASContracts } from "./generated/contracts";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle, Panel } from "./components";

type Proposal = CoastMASContracts["ProposalSpec"];
type Draft = CoastMASContracts["ProposalDraft"];
const revision = revisionSchema.extend({ spec: contract("ProposalSpec") });
const sceneRevision = revisionSchema.extend({ spec: contract("SceneSpec") });
const commentRevision = revisionSchema.extend({
  spec: contract("ProposalComment"),
});
const comparisonSchema = z.object({
  proposals: z.array(contract("ProposalSpec")),
  constraints: contract("ConstraintComparison"),
});
const states = {
  DRAFT: "草稿",
  SUBMITTED: "待人工审核",
  REVIEWED: "已人工审核",
  RETURNED: "退回修订",
};
const keyOf = (value: { id: string; version: number }) =>
  JSON.stringify([value.id, value.version]);

export default function Collaboration() {
  const { projectId } = useWorkspace();
  return <Workspace key={projectId} projectId={projectId} />;
}
function Workspace({ projectId }: { projectId: string }) {
  const client = useQueryClient();
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Proposal | null>(null);
  const [editing, setEditing] = useState(false);
  const [checked, setChecked] = useState<Proposal[]>([]);
  const access = useQuery({
    queryKey: ["collaboration-access", projectId],
    queryFn: ({ signal }) =>
      request(
        `/collaboration/access?project_id=${projectId}`,
        z.object({ user_id: z.string(), role: z.string() }),
        { signal },
      ),
  });
  const catalog = useQuery({
    queryKey: ["proposals", projectId, page],
    queryFn: ({ signal }) =>
      request(
        `/proposals?project_id=${projectId}&limit=50&offset=${page * 50}`,
        z.array(revision),
        { signal },
      ),
  });
  const compare = useMutation({
    mutationFn: (items: { id: string; version: number }[]) =>
      request("/proposals/compare", comparisonSchema, {
        method: "POST",
        body: {
          project_id: projectId,
          proposals: items.map(({ id, version }) => ({ id, version })),
        },
      }),
  });
  const refresh = async (spec: Proposal) => {
    setSelected(spec);
    setEditing(false);
    await client.invalidateQueries({ queryKey: ["proposals", projectId] });
  };
  return (
    <>
      <PageTitle
        title="协同方案"
        description="记录不同参与者的目标、硬约束和意见；比较事实与模型证据。人工审核不等于政策批准，系统不自动作出政策决定。"
      />
      <ErrorNotice error={catalog.error ?? access.error} />
      <Panel title="方案目录">
        <button
          disabled={!access.data || access.data.role === "VIEWER"}
          onClick={() => {
            setSelected(null);
            setEditing(true);
          }}
        >
          新建方案
        </button>
        {catalog.isPending ? (
          <Loading />
        ) : (
          <table>
            <thead>
              <tr>
                <th>比较</th>
                <th>方案</th>
                <th>版本</th>
                <th>角色</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {catalog.data?.map(({ spec }) => (
                <tr key={spec.id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`选择比较 ${spec.name}`}
                      checked={checked.some(
                        (item) => keyOf(item) === keyOf(spec),
                      )}
                      onChange={(event) =>
                        setChecked(
                          event.target.checked
                            ? [...checked, spec]
                            : checked.filter(
                                (item) => keyOf(item) !== keyOf(spec),
                              ),
                        )
                      }
                    />
                  </td>
                  <td>{spec.name}</td>
                  <td>v{spec.version}</td>
                  <td>{spec.author_role}</td>
                  <td>{states[spec.status ?? "DRAFT"]}</td>
                  <td>
                    <button
                      onClick={() => {
                        setSelected(spec);
                        setEditing(false);
                      }}
                    >
                      查看
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button disabled={page === 0} onClick={() => setPage(page - 1)}>
          上一页
        </button>
        <span>第 {page + 1} 页</span>
        <button
          disabled={(catalog.data?.length ?? 0) < 50}
          onClick={() => setPage(page + 1)}
        >
          下一页
        </button>
        <button
          disabled={!checked.length || checked.length > 20 || compare.isPending}
          onClick={() => compare.mutate(checked)}
        >
          比较所选版本（{checked.length}）
        </button>
        <button
          onClick={() => {
            setChecked([]);
            compare.reset();
          }}
        >
          清除比较
        </button>
      </Panel>
      {editing ? (
        <Editor
          key={selected ? keyOf(selected) : "new"}
          projectId={projectId}
          initial={selected}
          onSaved={refresh}
          onCancel={() => setEditing(false)}
        />
      ) : selected && access.data ? (
        <Detail
          key={keyOf(selected)}
          spec={selected}
          access={access.data}
          projectId={projectId}
          onEdit={() => setEditing(true)}
          onChanged={refresh}
          onCompare={() =>
            compare.mutate([
              { id: selected.id, version: selected.version - 1 },
              selected,
            ])
          }
        />
      ) : null}
      <ErrorNotice error={compare.error} />
      {compare.data ? (
        <Panel title="方案版本比较">
          <p>
            权重按各方原值展示，不合并为自动决策。区间冲突不能由目标高分抵消；不同场景的范围和时期须一并判断。
          </p>
          <table>
            <thead>
              <tr>
                <th>方案 / 版本</th>
                <th>固定场景</th>
                <th>目标权重</th>
                <th>依据</th>
                <th>真实结果引用</th>
              </tr>
            </thead>
            <tbody>
              {compare.data.proposals.map((item) => (
                <tr key={keyOf(item)}>
                  <td>
                    {item.name} v{item.version}
                  </td>
                  <td>
                    {item.scene.id} v{item.scene.version}
                  </td>
                  <td>
                    {item.objectives
                      .map(
                        (objective) => `${objective.name}: ${objective.weight}`,
                      )
                      .join("；")}
                  </td>
                  <td>{item.rationale}</td>
                  <td>
                    {item.evidence_results?.map((id) => (
                      <Link key={id} to={`/results/${encodeURIComponent(id)}`}>
                        查看结果 {id}
                      </Link>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {compare.data.constraints.conflicts.length === 0 ? (
            <p>未发现已录入区间的数值冲突；这不代表完整政策可行性。</p>
          ) : (
            compare.data.constraints.conflicts.map((item) => (
              <div role="alert" key={item.metric}>
                <strong>{item.code}</strong>
                <p>
                  {item.metric}：{item.minimum ?? "无下界"} 至{" "}
                  {item.maximum ?? "无上界"} {item.unit}
                </p>
                <p>
                  来源：
                  {item.sources
                    .map(
                      (source) =>
                        `${source.proposal_id} v${source.version} / ${source.constraint_id}`,
                    )
                    .join("；")}
                </p>
              </div>
            ))
          )}
          <table>
            <thead>
              <tr>
                <th>指标</th>
                <th>统一单位</th>
                <th>交集下界</th>
                <th>交集上界</th>
              </tr>
            </thead>
            <tbody>
              {compare.data.constraints.intersections.map((item) => (
                <tr key={item.metric}>
                  <td>{item.metric}</td>
                  <td>{item.unit}</td>
                  <td>{item.minimum ?? "无下界"}</td>
                  <td>{item.maximum ?? "无上界"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}
    </>
  );
}
function Editor({
  projectId,
  initial,
  onSaved,
  onCancel,
}: {
  projectId: string;
  initial: Proposal | null;
  onSaved: (value: Proposal) => Promise<void>;
  onCancel: () => void;
}) {
  const [identity] = useState(() => initial?.id ?? crypto.randomUUID());
  const [name, setName] = useState(initial?.name ?? "");
  const [rationale, setRationale] = useState(initial?.rationale ?? "");
  const [sceneKey, setSceneKey] = useState(initial ? keyOf(initial.scene) : "");
  const [scenePage, setScenePage] = useState(0);
  const [objectives, setObjectives] = useState(
    () =>
      initial?.objectives.map((item) => ({
        ...item,
        weight: String(item.weight),
      })) ?? [],
  );
  const [constraints, setConstraints] = useState(
    () =>
      initial?.constraints.map((item) => ({
        ...item,
        minimum: item.minimum == null ? "" : String(item.minimum),
        maximum: item.maximum == null ? "" : String(item.maximum),
      })) ?? [],
  );
  const [evidence, setEvidence] = useState(
    initial?.evidence_results?.join(", ") ?? "",
  );
  const scenes = useQuery({
    queryKey: ["collaboration-scenes", projectId, scenePage],
    queryFn: ({ signal }) =>
      request(
        `/collaboration/scenes?project_id=${projectId}&limit=50&offset=${scenePage * 50}`,
        z.array(sceneRevision),
        { signal },
      ),
  });
  const save = useMutation({
    mutationFn: async () => {
      const ref = z.tuple([z.string(), z.number()]).parse(JSON.parse(sceneKey));
      const value = contract("ProposalDraft").parse({
        id: identity,
        name,
        version: (initial?.version ?? 0) + 1,
        scene: { id: ref[0], version: ref[1] },
        rationale,
        objectives: objectives.map((item) => ({
          ...item,
          weight: item.weight.trim() === "" ? NaN : Number(item.weight),
        })),
        constraints: constraints.map((item) => ({
          ...item,
          minimum: item.minimum.trim() === "" ? null : Number(item.minimum),
          maximum: item.maximum.trim() === "" ? null : Number(item.maximum),
        })),
        evidence_results: evidence
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
      } satisfies Omit<Draft, "objectives"> & { objectives: unknown });
      return request("/proposals", revision, {
        method: "POST",
        body: {
          project_id: projectId,
          spec: value,
          expected_version: initial?.version ?? null,
        },
      });
    },
    onSuccess: (result) => onSaved(result.spec),
  });
  return (
    <Panel title={initial ? "修订方案" : "新建方案"}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <ErrorNotice error={save.error ?? scenes.error} />
        <label>
          方案名称
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          依据与意见
          <textarea
            required
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
          />
        </label>
        <label>
          固定场景
          <select
            required
            value={sceneKey}
            onChange={(event) => setSceneKey(event.target.value)}
          >
            <option value="">选择可访问的场景版本</option>
            {initial &&
            !scenes.data?.some(
              (row) => keyOf(row.spec) === keyOf(initial.scene),
            ) ? (
              <option value={keyOf(initial.scene)}>
                原场景 v{initial.scene.version}
              </option>
            ) : null}
            {scenes.data?.map((row) => (
              <option key={keyOf(row.spec)} value={keyOf(row.spec)}>
                {row.spec.name} · v{row.version}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={scenePage === 0}
          onClick={() => setScenePage(scenePage - 1)}
        >
          上一页场景
        </button>
        <button
          type="button"
          disabled={(scenes.data?.length ?? 0) < 50}
          onClick={() => setScenePage(scenePage + 1)}
        >
          下一页场景
        </button>
        <h3>目标及相对权重</h3>
        {objectives.map((item, index) => (
          <fieldset key={index}>
            <legend>目标 {index + 1}</legend>
            <label>
              目标标识 {index + 1}
              <input
                required
                value={item.objective_id}
                onChange={(event) =>
                  setObjectives(
                    objectives.map((value, i) =>
                      i === index
                        ? { ...value, objective_id: event.target.value }
                        : value,
                    ),
                  )
                }
              />
            </label>
            <label>
              目标名称 {index + 1}
              <input
                required
                value={item.name}
                onChange={(event) =>
                  setObjectives(
                    objectives.map((value, i) =>
                      i === index
                        ? { ...value, name: event.target.value }
                        : value,
                    ),
                  )
                }
              />
            </label>
            <label>
              目标权重 {index + 1}
              <input
                required
                type="number"
                min="0"
                step="any"
                value={item.weight}
                onChange={(event) =>
                  setObjectives(
                    objectives.map((value, i) =>
                      i === index
                        ? { ...value, weight: event.target.value }
                        : value,
                    ),
                  )
                }
              />
            </label>
            <button
              type="button"
              onClick={() =>
                setObjectives(objectives.filter((_, i) => i !== index))
              }
            >
              删除目标 {index + 1}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          onClick={() =>
            setObjectives([
              ...objectives,
              { objective_id: "", name: "", weight: "" },
            ])
          }
        >
          添加目标
        </button>
        <h3>硬约束</h3>
        <p>
          相同指标标识用于比较。单位必须明确，至少填写一个边界；空值表示无该边界。
        </p>
        {constraints.map((item, index) => (
          <fieldset key={item.constraint_id}>
            <legend>约束 {index + 1}</legend>
            {(["metric", "unit", "minimum", "maximum"] as const).map(
              (field) => (
                <label key={field}>
                  {
                    {
                      metric: "约束指标",
                      unit: "约束单位",
                      minimum: "约束下界",
                      maximum: "约束上界",
                    }[field]
                  }{" "}
                  {index + 1}
                  <input
                    required={field === "metric" || field === "unit"}
                    type={
                      field === "minimum" || field === "maximum"
                        ? "number"
                        : "text"
                    }
                    step="any"
                    value={item[field]}
                    onChange={(event) =>
                      setConstraints(
                        constraints.map((value, i) =>
                          i === index
                            ? { ...value, [field]: event.target.value }
                            : value,
                        ),
                      )
                    }
                  />
                </label>
              ),
            )}
            <button
              type="button"
              onClick={() =>
                setConstraints(constraints.filter((_, i) => i !== index))
              }
            >
              删除约束 {index + 1}
            </button>
          </fieldset>
        ))}
        <button
          type="button"
          onClick={() =>
            setConstraints([
              ...constraints,
              {
                constraint_id: crypto.randomUUID(),
                metric: "",
                unit: "",
                minimum: "",
                maximum: "",
              },
            ])
          }
        >
          添加硬约束
        </button>
        <label>
          已有结果编号（可选，逗号分隔）
          <input
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
          />
        </label>
        <p>
          仅可引用本项目、此固定场景的实际成功运行结果。公众角色不能添加未公开的运行结果。
        </p>
        <button disabled={save.isPending || !objectives.length} type="submit">
          保存方案版本
        </button>
        <button type="button" onClick={onCancel}>
          取消编辑
        </button>
      </form>
    </Panel>
  );
}
function Detail({
  spec,
  access,
  projectId,
  onEdit,
  onChanged,
  onCompare,
}: {
  spec: Proposal;
  access: { user_id: string; role: string };
  projectId: string;
  onEdit: () => void;
  onChanged: (value: Proposal) => Promise<void>;
  onCompare: () => void;
}) {
  const [version, setVersion] = useState(spec.version);
  const [opinion, setOpinion] = useState("");
  const [opinionKey, setOpinionKey] = useState(() => crypto.randomUUID());
  const [reviewText, setReviewText] = useState("");
  const client = useQueryClient();
  const path = `/proposals/${encodeURIComponent(spec.id)}`;
  const history = useQuery({
    queryKey: ["proposal-history", spec.id, spec.version],
    queryFn: ({ signal }) =>
      request(path + "/versions", z.array(revision), { signal }),
  });
  const current =
    history.data?.find((row) => row.version === version)?.spec ?? spec;
  const comments = useQuery({
    queryKey: ["proposal-comments", spec.id, version],
    queryFn: ({ signal }) =>
      request(
        `${path}/comments?version=${version}&limit=500`,
        z.array(commentRevision),
        { signal },
      ),
  });
  const submit = useMutation({
    mutationFn: () =>
      request(path + "/submit", revision, {
        method: "POST",
        body: { expected_version: spec.version },
      }),
    onSuccess: (result) => onChanged(result.spec),
  });
  const review = useMutation({
    mutationFn: (conclusion: "REVIEWED" | "RETURNED") =>
      request(path + "/review", revision, {
        method: "POST",
        body: {
          expected_version: spec.version,
          conclusion,
          rationale: reviewText,
        },
      }),
    onSuccess: (result) => onChanged(result.spec),
  });
  const publish = useMutation({
    mutationFn: (published: boolean) =>
      request(path + "/publication", z.object({ published: z.boolean() }), {
        method: "PUT",
        body: { expected_version: spec.version, published },
      }),
  });
  const note = useMutation({
    mutationFn: () =>
      request(path + "/comments", commentRevision, {
        method: "POST",
        body: {
          proposal_version: version,
          content: opinion,
          idempotency_key: opinionKey,
        },
      }),
    onSuccess: async () => {
      setOpinion("");
      setOpinionKey(crypto.randomUUID());
      await client.invalidateQueries({
        queryKey: ["proposal-comments", spec.id, version],
      });
    },
  });
  const own = access.user_id === spec.author_id;
  const manager = ["ADMIN", "MANAGER"].includes(access.role);
  const latest = version === spec.version;
  return (
    <Panel title={spec.name}>
      <p>
        {latest ? `当前版本：v${version}` : `历史版本：v${version}（只读）`}
      </p>
      <p>
        状态：{states[current.status ?? "DRAFT"]} · 作者角色：
        {current.author_role}
      </p>
      <ErrorNotice
        error={
          history.error ??
          comments.error ??
          submit.error ??
          review.error ??
          publish.error ??
          note.error
        }
      />
      <p>{current.rationale}</p>
      <p>
        固定场景：{current.scene.id} v{current.scene.version}
      </p>
      <ul>
        {current.objectives.map((item) => (
          <li key={item.objective_id}>
            {item.name}：{item.weight}
          </li>
        ))}
      </ul>
      <ul>
        {current.constraints.map((item) => (
          <li key={item.constraint_id}>
            {item.metric}：{item.minimum ?? "无下界"} 至{" "}
            {item.maximum ?? "无上界"} {item.unit}
          </li>
        ))}
      </ul>
      {current.evidence_results?.map((id) => (
        <p key={id}>
          <Link to={`/results/${encodeURIComponent(id)}`}>
            查看固定结果 {id}
          </Link>
        </p>
      ))}
      {current.review ? (
        <p>
          审核人：{current.review.reviewer_id} · {current.review.reviewed_at} ·{" "}
          {current.review.rationale}
        </p>
      ) : null}
      {history.data?.map((row) => (
        <button key={row.version} onClick={() => setVersion(row.version)}>
          查看 v{row.version}
        </button>
      ))}
      {latest && own && access.role !== "VIEWER" ? (
        <>
          <button onClick={onEdit}>编辑为新版本</button>
          <button
            disabled={
              submit.isPending ||
              !["DRAFT", "RETURNED"].includes(spec.status ?? "DRAFT")
            }
            onClick={() => submit.mutate()}
          >
            提交人工审核
          </button>
        </>
      ) : null}
      {latest && spec.version > 1 ? (
        <button onClick={onCompare}>与上一版本比较</button>
      ) : null}
      {latest && manager && !own && spec.status === "SUBMITTED" ? (
        <>
          <label>
            人工审核意见
            <textarea
              value={reviewText}
              onChange={(event) => setReviewText(event.target.value)}
            />
          </label>
          <button
            disabled={review.isPending || !reviewText.trim()}
            onClick={() => review.mutate("REVIEWED")}
          >
            记录审核完成
          </button>
          <button
            disabled={review.isPending || !reviewText.trim()}
            onClick={() => review.mutate("RETURNED")}
          >
            退回修订
          </button>
        </>
      ) : null}
      {latest && manager ? (
        <>
          <button
            disabled={publish.isPending || spec.status !== "REVIEWED"}
            onClick={() => publish.mutate(true)}
          >
            向公众公开方案
          </button>
          <button
            disabled={publish.isPending}
            onClick={() => publish.mutate(false)}
          >
            撤回公开
          </button>
          {publish.data ? (
            <p>{publish.data.published ? "方案已公开" : "方案未公开"}</p>
          ) : null}
        </>
      ) : null}
      <h3>此版本意见记录</h3>
      {comments.isPending ? (
        <Loading />
      ) : (
        comments.data?.map((row) => (
          <article key={row.resource_id}>
            <p>{row.spec.content}</p>
            <small>
              {row.spec.author_role} · {row.spec.author_id} ·{" "}
              {row.spec.created_at}
            </small>
          </article>
        ))
      )}
      {access.role !== "VIEWER" ? (
        <>
          <label>
            新增意见
            <textarea
              value={opinion}
              onChange={(event) => {
                setOpinion(event.target.value);
                setOpinionKey(crypto.randomUUID());
              }}
            />
          </label>
          <button
            disabled={note.isPending || !opinion.trim()}
            onClick={() => note.mutate()}
          >
            记录意见
          </button>
        </>
      ) : null}
      <p>
        项目：{projectId}
        。修订会清除旧审核结论并撤回公开，历史意见保留在原版本。
      </p>
    </Panel>
  );
}
