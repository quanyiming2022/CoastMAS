import { useEffect, useId, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Files, MoreHorizontal, Plus, Search } from "lucide-react";
import { api, jobSchema, type Asset } from "./api";
import { Modal } from "./ManagedCatalog";
import { ErrorNotice } from "./shared";
import type { TaskRecord } from "./draft";
const runPage = z.object({
  items: z.array(
    jobSchema.extend({ created: z.number(), draft_revision: z.number() }),
  ),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
});
export { runLabels } from "./shared";
import { runLabels } from "./shared";

function Runs({
  taskId,
  viewed,
  onView,
  revision,
}: {
  taskId: string;
  viewed: string | null;
  onView: (id: string) => void;
  revision: number | undefined;
}) {
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [offset, setOffset] = useState(0);
  const [copyError, setCopyError] = useState<unknown>(null);
  const [detail, setDetail] = useState<z.infer<typeof jobSchema> | null>(null),
    [copied, setCopied] = useState(false);
  const listing = useQuery({
    queryKey: ["research-runs", taskId, query, status, offset],
    queryFn: () =>
      api(
        `/tasks/${taskId}/jobs?${new URLSearchParams({ query, status, offset: String(offset), limit: "10" })}`,
        runPage,
      ),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => ["queued", "running"].includes(j.status))
        ? 1000
        : false,
  });
  const { refetch } = listing;
  useEffect(() => {
    void refetch();
  }, [revision, refetch]);
  return (
    <div className="content-tab-body">
      <div className="content-searchbar">
        <input
          aria-label="查找运行编号"
          type="search"
          placeholder="查找运行编号"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
        <select
          aria-label="运行状态"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">全部状态</option>
          {Object.entries(runLabels).map(([key, value]) => (
            <option key={key} value={key}>
              {value}
            </option>
          ))}
        </select>
      </div>
      <div className="content-scroll">
        <ErrorNotice error={listing.error} />
        {listing.isFetching ? <p role="status">正在读取运行…</p> : null}
        {!listing.isPending && !listing.error && !listing.data?.items.length ? (
          <p>{query || status ? "没有匹配的运行" : "尚无运行记录"}</p>
        ) : null}
        <ol className="compact-runs">
          {listing.data?.items.map((job) => (
            <li key={job.id} data-current={job.id === viewed}>
              <div>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => onView(job.id)}
                  aria-current={job.id === viewed ? "true" : undefined}
                >
                  #{job.id.slice(0, 8)}
                  {job.id === viewed ? " · 查看中" : ""}
                </button>
                <span>{runLabels[job.status] ?? "未知状态"}</span>
              </div>
              <div>
                <time dateTime={new Date(job.created * 1000).toISOString()}>
                  {new Date(job.created * 1000).toLocaleString("zh-CN", {
                    hour12: false,
                  })}
                </time>
                <span>v{job.draft_revision}</span>
                <button
                  type="button"
                  className="secondary"
                  aria-label={`运行 ${job.id.slice(0, 8)} 详情`}
                  onClick={() => {
                    setDetail(job);
                    setCopied(false);
                    setCopyError(null);
                  }}
                >
                  <MoreHorizontal size={16} />
                </button>
              </div>
            </li>
          ))}
        </ol>
      </div>
      <div className="content-pagination">
        <button
          type="button"
          className="secondary"
          disabled={!offset}
          onClick={() => setOffset((value) => Math.max(0, value - 10))}
        >
          上一页
        </button>
        <span>
          {listing.data
            ? `${Math.floor(offset / 10) + 1} / ${Math.max(1, Math.ceil(listing.data.total / 10))} · ${listing.data.total}项`
            : "读取中"}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={!listing.data || offset + 10 >= listing.data.total}
          onClick={() => setOffset((value) => value + 10)}
        >
          下一页
        </button>
      </div>
      {detail ? (
        <Modal title="运行详情" close={() => setDetail(null)}>
          <p>完整运行编号：{detail.id}</p>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              void navigator.clipboard
                .writeText(detail.id)
                .then(() => setCopied(true))
                .catch(setCopyError)
            }
          >
            {copied ? "已复制" : "复制运行编号"}
          </button>
          <ErrorNotice error={copyError} />
          <p>
            计算：{runLabels[detail.status] ?? detail.status}（{detail.status}）
          </p>
          <p>
            显示：{viewed === detail.id ? "当前查看此运行" : "未切换到此运行"}
          </p>
          <p>
            业务验证：此列表不依据计算成功推断业务有效；以固定成果的科学核验记录为准。
          </p>
          {detail.error ? <p role="alert">{detail.error.message}</p> : null}
        </Modal>
      ) : null}
    </div>
  );
}
export function ResearchContentManager({
  task,
  assets,
  runCount,
  viewedRun,
  preferredTab,
  savedTab,
  inputError,
  inputsLoading = false,
  onTab,
  children,
  onInspect,
  onAdd,
  onRemove,
  onViewRun,
  canEdit,
}: {
  task?: TaskRecord;
  assets: Asset[];
  runCount: number | undefined;
  viewedRun: string | null;
  inputError?: unknown;
  inputsLoading?: boolean;
  savedTab?: "layers" | "inputs" | "runs";
  onTab?: (tab: "layers" | "inputs" | "runs") => void;
  preferredTab: "layers" | "inputs";
  children: ReactNode;
  onInspect: (id: string) => void;
  onAdd: (kind: "library" | "upload" | "source") => void;
  onRemove: (id: string) => Promise<void>;
  onViewRun: (id: string) => void;
  canEdit: boolean;
}) {
  const [manualTab, setManualTab] = useState<
    "layers" | "inputs" | "runs" | null
  >(null);
  const tab = savedTab ?? manualTab ?? preferredTab;
  const [query, setQuery] = useState(""),
    [profile, setProfile] = useState("");
  const [remove, setRemove] = useState<Asset | null>(null),
    [pending, setPending] = useState(false),
    [error, setError] = useState<unknown>(null);
  const addId = useId();
  const filtered = assets.filter(
    (asset) =>
      (!query ||
        asset.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())) &&
      (!profile || asset.facts.profile === profile),
  );
  return (
    <aside className="research-content-manager" aria-label="研究内容管理器">
      <div className="content-tabs" role="tablist" aria-label="研究内容">
        {(["layers", "inputs", "runs"] as const).map((value) => (
          <button
            type="button"
            role="tab"
            id={`${addId}-tab-${value}`}
            aria-controls={`${addId}-panel-${value}`}
            tabIndex={tab === value ? 0 : -1}
            onKeyDown={(event) => {
              const keys = ["layers", "inputs", "runs"] as const;
              const index = keys.indexOf(value);
              const next =
                event.key === "ArrowRight"
                  ? (index + 1) % 3
                  : event.key === "ArrowLeft"
                    ? (index + 2) % 3
                    : event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? 2
                        : -1;
              if (next >= 0) {
                event.preventDefault();
                const target =
                  event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>(
                    "[role=tab]",
                  )[next];
                target?.focus();
                target?.click();
              }
            }}
            key={value}
            aria-selected={tab === value}
            className={tab === value ? "active" : "secondary"}
            onClick={() => {
              setManualTab(value);
              onTab?.(value);
            }}
          >
            {value === "layers"
              ? "图层"
              : value === "inputs"
                ? `输入 ${assets.length}`
                : `运行 ${runCount ?? "…"}`}
          </button>
        ))}
      </div>
      <div
        className="content-layer-tab content-tab-body"
        role="tabpanel"
        id={`${addId}-panel-layers`}
        aria-labelledby={`${addId}-tab-layers`}
        hidden={tab !== "layers"}
      >
        {children}
      </div>
      <div
        className="content-tab-body"
        role="tabpanel"
        id={`${addId}-panel-inputs`}
        aria-labelledby={`${addId}-tab-inputs`}
        hidden={tab !== "inputs"}
      >
        <div className="content-input-tools">
          <span>输入资料 {assets.length}项</span>
          <button
            type="button"
            className="secondary"
            onClick={() => onAdd("upload")}
            disabled={!task || !canEdit}
          >
            <Plus size={15} />
            添加资料
          </button>
        </div>
        <div className="content-searchbar">
          <Search size={15} aria-hidden="true" />
          <input
            type="search"
            aria-label="搜索当前输入"
            placeholder="搜索当前输入"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            aria-label="输入资料类型"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
          >
            <option value="">全部类型</option>
            {[...new Set(assets.map((asset) => asset.facts.profile))].map(
              (value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ),
            )}
          </select>
        </div>
        <div className="content-scroll">
          <p className="content-context">
            当前草稿 v{task?.revision ?? "—"}；历史成果引用保持不变。
          </p>
          <ErrorNotice error={error ?? inputError} />
          {inputsLoading ? <p role="status">正在读取研究输入…</p> : null}
          {!filtered.length && !inputsLoading && !inputError ? (
            <p>{assets.length ? "无匹配输入" : "当前研究尚未绑定输入"}</p>
          ) : (
            <ul className="compact-inputs">
              {filtered.map((asset) => (
                <li key={asset.id}>
                  <Files size={16} aria-hidden="true" />
                  <button
                    className="text-button input-name"
                    type="button"
                    title={asset.name}
                    onClick={() => onInspect(asset.id)}
                  >
                    {asset.name}
                  </button>
                  <span>{asset.facts.profile}</span>
                  <button
                    type="button"
                    className="secondary"
                    disabled={!canEdit}
                    aria-label={`移除输入 ${asset.name}`}
                    onClick={() => setRemove(asset)}
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div
        className="content-tab-body"
        role="tabpanel"
        id={`${addId}-panel-runs`}
        aria-labelledby={`${addId}-tab-runs`}
        hidden={tab !== "runs"}
      >
        {task ? (
          <Runs
            key={task.id}
            taskId={task.id}
            viewed={viewedRun}
            onView={onViewRun}
            revision={runCount}
          />
        ) : (
          <p>没有活动研究。</p>
        )}
      </div>
      {remove ? (
        <Modal title="核对移除输入的影响" close={() => setRemove(null)}>
          <p>{remove.name}</p>
          <p>
            将移除当前草稿的输入引用及{" "}
            {task?.draft.mapping.filter((m) => m.asset_id === remove.id)
              .length ?? 0}{" "}
            项变量绑定；相关步骤需重新预检。原始资产、共享方法与历史成果保留。
          </p>
          <ErrorNotice error={error} />
          <button
            type="button"
            disabled={pending}
            onClick={async () => {
              setPending(true);
              try {
                await onRemove(remove.id);
                setRemove(null);
              } catch (problem) {
                setError(problem);
              } finally {
                setPending(false);
              }
            }}
          >
            确认移除输入
          </button>
        </Modal>
      ) : null}
    </aside>
  );
}
