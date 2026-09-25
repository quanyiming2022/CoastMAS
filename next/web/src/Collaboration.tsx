import {
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, APIError } from "./api";
import { ErrorNotice } from "./shared";
import { saveMessage, type AdditionalSaveGuard } from "./useTaskDraft";
import { OpinionSession, OpinionConflict, type Opinion } from "./opinionDraft";
const opinionSchema = z.object({
  revision: z.number(),
  text: z.string(),
  perspective: z.string().nullable(),
});
const reviewSchema = z.object({
  revision: z.number(),
  status: z.enum(["unreviewed", "reviewed", "changes_requested"]),
});
const stateSchema = z.object({
  review: reviewSchema,
  can_comment: z.boolean(),
  can_review: z.boolean(),
  draft_revision: z.number(),
});
const commentSchema = z.object({
  id: z.string(),
  author: z.string(),
  text: z.string(),
  perspective: z.string(),
  created: z.number(),
});
const reviewsSchema = z.object({
  id: z.string(),
  author: z.string(),
  note: z.string(),
  status: z.string(),
  revision: z.number(),
  created: z.number(),
});
const labels: Record<string, string> = {
  unreviewed: "尚未审核",
  reviewed: "技术核对通过",
  changes_requested: "需要修改",
  research: "科研视角",
  management: "管理视角",
  public: "公众视角",
};
type GuardChange = (guard: AdditionalSaveGuard | null) => void;
function History({
  base,
  kind,
}: {
  base: string;
  kind: "comments" | "reviews";
}) {
  const [page, setPage] = useState(0);
  const result = useQuery({
    queryKey: ["discussion", base, kind, page],
    queryFn: () =>
      api(
        `${base}/${kind}?limit=25&offset=${page * 25}`,
        z.object({
          total: z.number(),
          items: z.array(z.union([commentSchema, reviewsSchema])),
        }),
      ),
  });
  return (
    <div>
      <ErrorNotice error={result.error} />
      {result.isPending ? (
        <p role="status">正在读取协同记录…</p>
      ) : result.data?.total === 0 ? (
        <p>{kind === "comments" ? "暂无已发布意见" : "暂无审核记录"}</p>
      ) : null}
      {result.data?.items.map((item) => (
        <article className="discussion-entry" key={item.id}>
          <p>
            <strong>{item.author}</strong> ·{" "}
            {new Date(item.created * 1000).toLocaleString()} ·{" "}
            {"perspective" in item
              ? labels[item.perspective]
              : `${labels[item.status]} · 第${item.revision}次`}
          </p>
          <p className="preserve-lines">
            {"text" in item ? item.text : item.note}
          </p>
        </article>
      ))}
      {result.data && result.data.total > 0 ? (
        <div className="pagination">
          <span>
            {page + 1} / {Math.ceil(result.data.total / 25)} 页 · 共{" "}
            {result.data.total} 条
          </span>
          <button
            type="button"
            className="secondary"
            disabled={!page}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <button
            type="button"
            className="secondary"
            disabled={(page + 1) * 25 >= result.data.total}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      ) : null}
    </div>
  );
}
function OpinionEditor({
  base,
  initial,
  review,
  canReview,
  onGuardChange,
}: {
  base: string;
  initial: Opinion;
  review: z.infer<typeof reviewSchema>;
  canReview: boolean;
  onGuardChange?: GuardChange;
}) {
  const opinionInputId = useId();
  const cache = useQueryClient();
  const [session] = useState(
    () =>
      new OpinionSession(initial, async (value) => {
        try {
          const saved = await api(base + "/draft", opinionSchema, {
            method: "PUT",
            body: JSON.stringify({
              expected_revision: value.revision,
              text: value.text,
              perspective: value.perspective,
            }),
          });
          cache.setQueryData(["opinion-draft", base], saved);
          return saved;
        } catch (error) {
          if (error instanceof APIError && error.status === 409) {
            const details = z
              .object({ remote: opinionSchema })
              .safeParse(error.details);
            if (details.success) throw new OpinionConflict(details.data.remote);
          }
          throw error;
        }
      }),
  );
  const snapshot = useSyncExternalStore(session.subscribe, session.snapshot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const attempt = useRef<{ signature: string; key: string } | null>(null);
  useEffect(() => {
    if (snapshot.status !== "unsaved") return;
    const timer = setTimeout(() => void session.save().catch(() => {}), 450);
    return () => clearTimeout(timer);
  }, [session, snapshot.status, snapshot.value]);
  useEffect(() => {
    onGuardChange?.({ dirty: snapshot.status !== "saved", save: session.save });
  }, [onGuardChange, session, snapshot.status]);
  useEffect(() => () => onGuardChange?.(null), [onGuardChange]);
  async function publish(status?: "reviewed" | "changes_requested") {
    setBusy(true);
    setError(null);
    try {
      await session.save();
      const value = session.snapshot().value;
      const signature = JSON.stringify({
        revision: value.revision,
        status,
        review: review.revision,
        text: value.text,
      });
      if (attempt.current?.signature !== signature)
        attempt.current = { signature, key: crypto.randomUUID() };
      const payload = status
        ? {
            expected_revision: review.revision,
            status,
            note: value.text,
            idempotency_key: attempt.current.key,
          }
        : {
            expected_revision: value.revision,
            idempotency_key: attempt.current.key,
          };
      await api(
        base + (status ? "/reviews" : "/comments"),
        z.object({ id: z.string() }),
        { method: "POST", body: JSON.stringify(payload) },
      );
      if (!status) session.replace(await api(base + "/draft", opinionSchema));
      await cache.invalidateQueries({ queryKey: ["discussion", base] });
      attempt.current = null;
    } catch (error) {
      setError(error);
      await cache.invalidateQueries({ queryKey: ["discussion", base] });
    } finally {
      setBusy(false);
    }
  }
  return (
    <fieldset className="task-controls" disabled={busy}>
      <h4>我的意见与审核说明</h4>
      <p role="status">{saveMessage(snapshot.status)}</p>
      <label htmlFor={opinionInputId}>意见内容</label>
      <textarea
        id={opinionInputId}
        rows={4}
        maxLength={10000}
        value={snapshot.value.text}
        onChange={(event) => session.edit({ text: event.target.value })}
      />
      <label htmlFor={`${opinionInputId}-perspective`}>
        讨论视角（发布意见时必选，不改变权限）
      </label>
      <select
        id={`${opinionInputId}-perspective`}
        value={snapshot.value.perspective ?? ""}
        onChange={(e) => session.edit({ perspective: e.target.value || null })}
      >
        <option value="">请选择视角</option>
        <option value="research">科研视角</option>
        <option value="management">管理视角</option>
        <option value="public">公众视角</option>
      </select>

      <ErrorNotice error={error ?? snapshot.error} />
      {snapshot.remote ? (
        <div role="alert">
          <p>本地与服务器草稿不一致，当前文字尚未覆盖服务器。</p>
          <p className="preserve-lines">服务器文字：{snapshot.remote.text}</p>
          <button
            type="button"
            className="secondary"
            onClick={() => session.useRemote()}
          >
            采用服务器草稿
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => session.keepLocal()}
          >
            保留本地并重新保存
          </button>
        </div>
      ) : null}
      {snapshot.status === "error" ? (
        <button
          type="button"
          className="secondary"
          onClick={() => void session.save().catch(setError)}
        >
          重试保存意见
        </button>
      ) : null}
      <div className="actions">
        <button
          type="button"
          disabled={
            !snapshot.value.text.trim() ||
            !snapshot.value.perspective ||
            !!snapshot.remote
          }
          onClick={() => void publish()}
        >
          发布意见
        </button>
        {canReview ? (
          <>
            <button
              type="button"
              className="secondary"
              disabled={!snapshot.value.text.trim() || !!snapshot.remote}
              onClick={() => void publish("reviewed")}
            >
              记录技术核对通过
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!snapshot.value.text.trim() || !!snapshot.remote}
              onClick={() => void publish("changes_requested")}
            >
              要求修改
            </button>
          </>
        ) : null}
      </div>
    </fieldset>
  );
}
export function Collaboration({
  jobId,
  onGuardChange,
}: {
  jobId: string;
  onGuardChange?: GuardChange;
}) {
  const base = `/jobs/${jobId}/discussion`;
  const state = useQuery({
    queryKey: ["discussion", base, "state"],
    queryFn: () => api(base, stateSchema),
  });
  const draft = useQuery({
    queryKey: ["opinion-draft", base],
    queryFn: () => api(base + "/draft", opinionSchema),
    enabled: state.data?.can_comment === true,
  });
  return (
    <section aria-label="协同意见与技术审核">
      <h3>协同意见与技术审核</h3>
      <p>
        意见和审核绑定当前查看的运行版本。修改方案后必须重新计算并核对；技术审核不等于正式科学认定或政策批准。
      </p>
      <ErrorNotice error={state.error ?? draft.error} />
      {state.data ? (
        <p>
          审核状态：{labels[state.data.review.status]} · 固定任务 v
          {state.data.draft_revision}
        </p>
      ) : null}
      {state.data?.can_comment && draft.data ? (
        <OpinionEditor
          key={jobId}
          base={base}
          initial={draft.data}
          review={state.data.review}
          canReview={state.data.can_review}
          onGuardChange={onGuardChange}
        />
      ) : null}
      {state.data && !state.data.can_comment ? (
        <p>当前角色可查看协同记录，不能发布或审核。</p>
      ) : null}
      <h4>已发布意见</h4>
      <History base={base} kind="comments" />
      <details className="disclosure">
        <summary>全部审核记录</summary>
        <History base={base} kind="reviews" />
      </details>
    </section>
  );
}
