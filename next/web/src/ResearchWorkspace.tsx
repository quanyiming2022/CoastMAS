import { PlanningDirectory, type PlanningReference } from "./PlanningDirectory";
import { taskFlows, taskType, taskTypes, type TaskType } from "./taskFlows";
import { ModelDirectory, MatchingDirectory } from "./DomainDirectory";
import { IndicatorDirectory } from "./IndicatorDirectory";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CircleHelp, X } from "lucide-react";
import {
  ResearchPanelProvider,
  type ResearchPanel,
} from "./ResearchPanels";
import { ResearchStepPanel, stepStatus } from "./ResearchStepPanel";
import {
  ResearchHeader,
  researchSaveStatus,
  combineSaveStatus,
  type DraftSummary,
} from "./ResearchHeader";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema, jobSchema, resultSchema } from "./api";
import { taskSchema, type TaskRecord } from "./draft";
import { MethodCatalog } from "./MethodCatalog";
import { CatalogDock } from "./CatalogDock";
import { Catalog } from "./Catalog";
import { AssetViewer } from "./AssetViewer";
import { LayerCatalog } from "./LayerCatalog";
import type { MapControls } from "./AssetMap";
import { ResearchContentManager } from "./ResearchContentManager";
import { ResearchEditor } from "./ResearchEditor";
import { ResultView } from "./ResultView";
import { ManagedCatalog, Modal, type CatalogRow } from "./ManagedCatalog";
import { useResearchState, initialResearch } from "./useResearchState";
import { useViewState, initialDisplay } from "./useViewState";
import { InputAttachmentClient, acceptsAttachment } from "./inputAttachment";
import { ErrorNotice } from "./shared";
import { useConfigurationReview } from "./ConfigurationReview";
export function ResearchWorkspace({
  project,
  canEdit,
  routeTaskId,
  hidden = false,
  headerHost,
}: {
  project: string;
  canEdit: boolean;
  routeTaskId?: string;
  hidden?: boolean;
  headerHost?: HTMLDivElement | null;
}) {
  const [methodEditorHost, setMethodEditorHost] =
    useState<HTMLDivElement | null>(null);
  const [methodEditing, setMethodEditing] = useState(false);
  const [attachmentClient] = useState(() => new InputAttachmentClient());
  const [attachmentMessage, setAttachmentMessage] = useState("");
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const [targetTask, setTargetTask] = useState("");
  const [resultLayerHost, setResultLayerHost] = useState<HTMLDivElement | null>(
    null,
  );
  const [resultViewSave, setResultViewSave] = useState<{
    owner: string;
    status: string;
  } | null>(null);
  const reportViewSave = useCallback(
    (owner: string, status: string) => setResultViewSave({ owner, status }),
    [],
  );
  const [draftSummary, setDraftSummary] = useState<DraftSummary | null>(null);
  const [activePanel, setActivePanel] = useState<ResearchPanel | null>(null);
  const [inspectorHost, setInspectorHost] = useState<HTMLDivElement | null>(
    null,
  );
  const rawMapControls = useRef<MapControls | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const panelHeading = useRef<HTMLHeadingElement>(null);
  const openPanel = useCallback(
    (next: ResearchPanel, trigger?: HTMLElement | null) => {
      returnFocus.current =
        trigger ??
        (document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null);
      setActivePanel(next);
      requestAnimationFrame(() => panelHeading.current?.focus());
    },
    [],
  );
  const closePanel = useCallback(() => {
    setActivePanel(null);
    requestAnimationFrame(() => {
      if (returnFocus.current?.isConnected) returnFocus.current.focus();
    });
  }, []);
  const cache = useQueryClient(),
    location = useLocation(),
    navigate = useNavigate();
  const context = useResearchState(`/projects/${project}/workspace-state`),
    state = context.active ?? initialResearch;
  const view = useViewState(`/projects/${project}/view-state`);
  const [failure, setFailure] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [creating, setCreating] = useState(false),
    [title, setTitle] = useState(""),
    [newTaskType, setNewTaskType] = useState<TaskType>("assessment"),
    [method, setMethod] = useState<CatalogRow | null>(null);
  useEffect(() => {
    if (!activePanel || hidden) return;
    const escape = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !document.querySelector(":modal, [popover]:popover-open")
      ) {
        event.preventDefault();
        closePanel();
        if (state.central_view === "configuration")
          void context
            .save({
              ...state,
              central_view: state.viewed_job_id ? "result" : "map",
            })
            .catch(setFailure);
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [activePanel, hidden, closePanel, state, context]);
  const controller = useRef<{
    save: () => Promise<void>;
    replace: (t: TaskRecord) => void;
    rename: (title: string) => Promise<void>;
    openAdd: (mode: "library" | "upload" | "source") => Promise<void>;
    removeInput: (id: string, revision: number) => Promise<void>;
  } | null>(null);
  const onController = useCallback((c: typeof controller.current) => {
    controller.current = c;
  }, []);
  const task = useQuery({
    queryKey: ["task", state.active_task_id],
    enabled: context.ready && !!state.active_task_id,
    queryFn: () => api(`/tasks/${state.active_task_id}`, taskSchema),
  });
  const configurationReview = useConfigurationReview(task.data);
  const currentTask = useRef<TaskRecord | undefined>(undefined);
  const currentResearch = useRef(state);
  useEffect(() => {
    currentTask.current = task.data;
    currentResearch.current = state;
    return () => { currentTask.current = undefined; };
  }, [task.data, state]);

  const attachTargets = useQuery({
    queryKey: ["attachment-targets", project],
    enabled: !!pendingInput,
    queryFn: () =>
      api(
        `/management/catalog/tasks?project=${project}&state=active&limit=100`,
        z.object({
          items: z.array(z.object({ id: z.string(), name: z.string() })),
        }),
      ),
  });
  const assets = useQuery({
    queryKey: ["task-assets", state.active_task_id, task.data?.revision],
    enabled: !!task.data,
    queryFn: () =>
      api(`/tasks/${state.active_task_id}/assets`, z.array(assetSchema)),
  });
  const history = useQuery({
    queryKey: ["jobs", state.active_task_id],
    enabled: !!task.data,
    queryFn: () =>
      api(
        `/tasks/${state.active_task_id}/jobs?limit=100`,
        z.object({ items: z.array(jobSchema), total: z.number() }),
      ),
    refetchInterval: (q) =>
      q.state.data?.items.some((j) => ["queued", "running"].includes(j.status))
        ? 800
        : false,
  });
  const inspected = useQuery({
    queryKey: ["asset", state.inspected_asset_id],
    enabled: context.ready && !!state.inspected_asset_id,
    queryFn: () => api(`/assets/${state.inspected_asset_id}`, assetSchema),
  });
  const currentJob = useQuery({
    queryKey: ["job", state.viewed_job_id],
    enabled: !!state.viewed_job_id,
    queryFn: () => api(`/jobs/${state.viewed_job_id}`, jobSchema),
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.status ?? "") ? 600 : false,
  });
  const result = useQuery({
    queryKey: ["result", state.viewed_job_id],
    enabled: currentJob.data?.status === "succeeded",
    queryFn: () => api(`/jobs/${state.viewed_job_id}/result`, resultSchema),
  });
  const activation = useRef("");
  useEffect(() => {
    if (
      !context.ready ||
      !routeTaskId ||
      activation.current === routeTaskId ||
      routeTaskId === state.active_task_id
    )
      return;
    activation.current = routeTaskId;
    void (async () => {
      try {
        const next = await api(`/tasks/${routeTaskId}`, taskSchema);
        if (next.project_id !== project) throw new Error("任务不属于当前项目");
        await context.save({
          ...state,
          active_task_id: next.id,
          viewed_job_id: null,
          inspected_asset_id:
            next.draft.selection[0]?.asset_id ?? state.inspected_asset_id,
          central_view: "map",
        });
      } catch (e) {
        setFailure(e);
      }
    })();
  }, [routeTaskId, context.ready, context, state, project]);
  const researchSteps = taskFlows[taskType(task.data)];
  const domainPanels: Record<string,string> = {"/models":"models", "/coupling/matching":"matching", "/planning/tasks":"planning", "/indicators":"indicators", "/planning/objectives":"objectives", "/planning/constraints":"constraints", "/planning/decisions":"decisions"};
  const panel = domainPanels[location.pathname] ?? (
    location.pathname === "/library"
      ? "data"
      : location.pathname === "/methods"
        ? "methods"
        : location.pathname === "/tasks" || location.pathname === "/"
          ? "tasks"
          : location.pathname === "/runs"
            ? "runs"
            : location.pathname === "/results"
              ? "results"
              : "research");
  async function perform(action: () => Promise<void>, saveCurrent = false) {
    setBusy(true);
    setFailure(null);
    try {
      if (saveCurrent) await controller.current?.save();
      await action();
    } catch (e) {
      setFailure(e);
    } finally {
      setBusy(false);
    }
  }
  async function inspect(id: string) {
    await view.save(initialDisplay(id));
    await context.save({
      ...state,
      inspected_asset_id: id,
      central_view: "map",
    });
  }
  async function applyPlanning(ref: PlanningReference) {
    await controller.current?.save();
    const active = currentTask.current;
    if (!active || taskType(active) !== "planning") throw new Error("请先继续一个规划任务");
    const saved = await api(`/v1/tasks/${active.id}/planning/bindings`, taskSchema, {
      method: "POST", headers: {"If-Match": `"${active.revision}"`}, body: JSON.stringify(ref),
    });
    controller.current?.replace(saved);
    cache.setQueryData(["task", saved.id], saved);
  }
  async function bind(id: string, target = task.data) {
    if (!target) {
      setPendingInput(id);
      return;
    }
    const targetId = target.id;
    if (currentTask.current?.id === targetId) await controller.current?.save();
    const fresh = await api(`/tasks/${targetId}`, taskSchema);
    setAttachmentMessage("正在加入研究…");
    const receipt = await attachmentClient.attachId(fresh, id);
    const row = receipt.items[0];
    if (!row) throw new Error("加入回执缺少资料项，请重新查询");
    if (row.status === "rejected") throw new Error(row.message ?? "资料未加入");
    const current = currentTask.current;
    if (acceptsAttachment(current, receipt))
      controller.current?.replace(receipt.task);
    const cached = cache.getQueryData<TaskRecord>(["task", targetId]);
    if (!cached || cached.revision <= receipt.task.revision)
      cache.setQueryData(["task", targetId], receipt.task);
    setAttachmentMessage(
      `${row.status === "already_present" ? "已在" : "已加入"}研究“${receipt.task.draft.title}” · 配置 v${receipt.task.revision}`,
    );
    await cache.invalidateQueries({ queryKey: ["task-assets", targetId] });
    setPendingInput(null);
  }
  async function applyMethod() {
    if (!method) return;
    let target = task.data;
    if (!target) {
      target = await api("/tasks", taskSchema, {
        method: "POST",
        body: JSON.stringify({
          project_id: project,
          title: method.name + " · 研究",
          purpose: method.purpose,
        }),
      });
    }
    const fresh = cache.getQueryData<TaskRecord>(["task", target.id]) ?? target;
    const next = await api(`/tasks/${target.id}/apply-method`, taskSchema, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: fresh.revision,
        method_id: method.id,
        method_revision: method.source_revision,
      }),
    });
    controller.current?.replace(next);
    cache.setQueryData(["task", next.id], next);
    await context.save({
      ...state,
      active_task_id: next.id,
    });
    setMethod(null);
    openPanel({ kind: "step", step: "sources", scope: "draft" });
  }
  async function showRun(row: CatalogRow) {
    const job = await api(
      "/jobs/" + row.id,
      jobSchema.extend({ task_id: z.string() }),
    );
    await context.save({
      ...state,
      active_task_id: job.task_id,
      viewed_job_id: job.id,
      central_view: "result",
    });
    navigate("/research?project=" + project);
  }
  async function execute() {
    if (!task.data) return;
    const fresh =
      cache.getQueryData<TaskRecord>(["task", task.data.id]) ?? task.data;
    const job = await api(`/tasks/${fresh.id}/execute`, jobSchema, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: fresh.revision,
        idempotency_key: crypto.randomUUID(),
      }),
    });
    await context.save({
      ...state,
      viewed_job_id: job.id,
      central_view: "result",
    });
    await cache.invalidateQueries({ queryKey: ["jobs", fresh.id] });
  }
  async function quality() {
    if (!task.data || !state.inspected_asset_id)
      throw new Error("选择当前任务内的一幅栅格后可运行质量工具");
    const fresh =
      cache.getQueryData<TaskRecord>(["task", task.data.id]) ?? task.data;
    const node = await api(
      `/tasks/${fresh.id}/processing-nodes`,
      z.object({ id: z.string() }),
      {
        method: "POST",
        body: JSON.stringify({
          expected_revision: fresh.revision,
          asset_id: state.inspected_asset_id,
          operator: "valid_mask",
          band: view.active?.band ?? 1,
          idempotency_key: crypto.randomUUID(),
        }),
      },
    );
    const job = await api(`/processing-nodes/${node.id}/execute`, jobSchema, {
      method: "POST",
      body: JSON.stringify({
        expected_revision: fresh.revision,
        idempotency_key: crypto.randomUUID(),
      }),
    });
    await context.save({
      ...state,
      viewed_job_id: job.id,
      central_view: "result",
    });
    await cache.invalidateQueries({ queryKey: ["jobs", fresh.id] });
  }
  if (!context.ready)
    return (
      <p role="status">
        正在恢复研究现场…
        <ErrorNotice error={context.error} />
      </p>
    );
  const displayed = inspected.data;
  const display =
    view.active?.asset_id === displayed?.id
      ? view.active
      : displayed
        ? initialDisplay(displayed.id)
        : null;
  const management = panel !== "research";
  const scienceSave = researchSaveStatus(
    context.ready,
    context.saving,
    context.error,
    !state.active_task_id
      ? "saved"
      : draftSummary?.taskId === task.data?.id
        ? (draftSummary?.status ?? null)
        : null,
  );
  const mapSave =
    state.central_view === "result" &&
    Array.isArray(result.data?.data.files) &&
    result.data.data.files.length > 0
      ? resultViewSave?.owner === state.viewed_job_id
        ? resultViewSave.status
        : "正在恢复…"
      : state.central_view === "map" && displayed
        ? researchSaveStatus(view.ready, view.saving, view.error, "saved")
        : "已保存";
  return (
    <ResearchPanelProvider
      value={{
        reportViewSave,
        active: activePanel,
        host: inspectorHost,
        open: openPanel,
        close: closePanel,
      }}
    >
      <div
        className="research-workspace"
        hidden={hidden}
        data-drawer={
          management
            ? state.drawer === "maximized"
              ? "maximized"
              : "open"
            : "closed"
        }
      >
        {headerHost && !hidden
          ? createPortal(
              <ResearchHeader
                title={
                  (draftSummary &&
                  task.data &&
                  draftSummary.taskId === task.data.id
                    ? draftSummary?.title
                    : task.data?.draft.title) ?? "工作台"
                }
                status={combineSaveStatus(scienceSave, mapSave)}
                statusDetail={`研究配置与现场：${scienceSave}；地图视图：${mapSave}。历史成果不因保存而重算。`}
                canEdit={canEdit}
                canExecute={!!task.data && !busy && canEdit}
                onNew={() => setCreating(true)}
                onExecute={() => void perform(execute, true)}
                onRename={
                  task.data
                    ? async (title) => {
                        if (!controller.current)
                          throw new Error("研究草稿尚未恢复");
                        await controller.current.rename(title);
                      }
                    : undefined
                }
              />,
              headerHost,
            )
          : null}
        <ErrorNotice
          error={
            failure ??
            context.error ??
            task.error ??
            inspected.error ??
            result.error
          }
        />
        {context.error ? (
          <button onClick={() => void context.restore().catch(setFailure)}>
            重新读取服务器现场
          </button>
        ) : null}
        <div
          className="research-body"
          data-flow={!!task.data}
          data-inspector={
            !!activePanel && state.central_view !== "configuration"
          }
          data-configuration={state.central_view === "configuration"}
        >
          <ResearchContentManager
            task={task.data}
            assets={assets.data ?? []}
            runCount={state.active_task_id ? history.data?.total : 0}
            inputError={assets.error}
            inputsLoading={assets.isPending && !!state.active_task_id}
            viewedRun={state.viewed_job_id}
            savedTab={state.content_tab}
            onTab={(tab) =>
              void context
                .save({ ...state, content_tab: tab })
                .catch(setFailure)
            }
            preferredTab={
              activePanel?.kind === "step" && activePanel.step === "sources"
                ? "inputs"
                : "layers"
            }
            canEdit={canEdit}
            onInspect={(id) => void inspect(id).catch(setFailure)}
            onAdd={(kind) => {
              void controller.current?.openAdd(kind).catch(setFailure);
            }}
            onRemove={async (id) => {
              if (!controller.current || !task.data)
                throw new Error("草稿尚未恢复");
              await controller.current.removeInput(id, task.data.revision);
            }}
            onViewRun={(id) => {
              closePanel();
              void context
                .save({ ...state, viewed_job_id: id, central_view: "result" })
                .catch(setFailure);
            }}
          >
            <div
              ref={setResultLayerHost}
              hidden={methodEditing || state.central_view !== "result"}
            />
            {state.central_view === "map" &&
            displayed &&
            display &&
            ["geotiff", "cog"].includes(displayed.facts.profile) ? (
              <LayerCatalog
                items={[
                  {
                    id: displayed.id,
                    name: displayed.name,
                    kind: displayed.facts.profile,
                    role: "reference",
                    visible: display.visible,
                  },
                ]}
                activeId={displayed.id}
                onSelect={() =>
                  openPanel({
                    kind: "details",
                    owner: `/assets/${displayed.id}`,
                  })
                }
                onVisibility={(_id, visible) =>
                  void view.save({ ...display, visible }).catch(setFailure)
                }
                onOrder={() => {}}
                onRemove={() =>
                  void context
                    .save({ ...state, inspected_asset_id: null })
                    .catch(setFailure)
                }
                onAction={(_id, action, trigger) => {
                  if (action === "locate") rawMapControls.current?.locate();
                  else if (action === "download") {
                    const link = document.createElement("a");
                    link.href = `/api/assets/${displayed.id}/download`;
                    link.download = "";
                    link.click();
                  } else
                    openPanel(
                      {
                        kind: action === "style" ? "style" : "details",
                        owner: `/assets/${displayed.id}`,
                      },
                      trigger,
                    );
                }}
              />
            ) : null}
            {state.central_view === "map" &&
            displayed &&
            !["geotiff", "cog"].includes(displayed.facts.profile) ? (
              <p>当前资料使用表格或文件视图，没有可显示的地图图层。</p>
            ) : null}
            {!result.data && !displayed ? (
              <p>尚无成果图层；已定位资料可在数据资源中直接查看。</p>
            ) : null}
          </ResearchContentManager>
          <div className="research-visual">
            <div
              ref={setMethodEditorHost}
              className="research-method-edit-host"
              hidden={!methodEditing}
            />
            <div className="research-view-tabs" hidden={methodEditing}>
              {(["map", "configuration", "result"] as const).map((v) => (
                <button
                  key={v}
                  aria-pressed={state.central_view === v}
                  className={state.central_view === v ? "" : "secondary"}
                  disabled={
                    v === "configuration" && !task.data?.draft.mapping.length
                  }
                  onClick={() => {
                    closePanel();
                    void context
                      .save({ ...state, central_view: v })
                      .catch(setFailure);
                  }}
                >
                  {
                    {
                      map: "地图与资料",
                      configuration: "分析配置与步骤",
                      result: "当前运行成果",
                    }[v]
                  }
                </button>
              ))}
            </div>
            <div
              className="research-map catalog-detail"
              hidden={methodEditing || state.central_view !== "map"}
            >
              {displayed && display ? (
                <AssetViewer
                  key={displayed.id}
                  controls={rawMapControls}
                  asset={displayed}
                  state={display}
                  onChange={(s) => void view.save(s).catch(setFailure)}
                />
              ) : (
                <div className="research-empty">
                  <p>暂无可显示图层</p>
                  {!(
                    activePanel?.kind === "step" &&
                    activePanel.step === "sources"
                  ) ? (
                    <button
                      type="button"
                      onClick={() => navigate("/library?project=" + project)}
                    >
                      查看资料
                    </button>
                  ) : null}
                </div>
              )}
            </div>
            <div
              className="research-result"
              hidden={state.central_view !== "result"}
            >
              {result.data && state.viewed_job_id ? (
                <>
                  <ResultView
                    jobId={state.viewed_job_id}
                    data={result.data.data}
                    layerHost={resultLayerHost}
                    currentRevision={task.data?.revision}
                    historical={
                      !!history.data?.items[0] &&
                      history.data.items[0].id !== state.viewed_job_id
                    }
                  />
                </>
              ) : (
                <p>
                  {currentJob.data
                    ? `运行状态：${({ queued: "排队中", running: "计算中", failed: "计算失败", cancelled: "已取消", succeeded: "计算完成" } as Record<string, string>)[currentJob.data.status] ?? currentJob.data.status}${currentJob.data.error ? " · " + currentJob.data.error.message : ""}`
                    : "尚未选择运行成果"}
                </p>
              )}
            </div>
          </div>
          <aside
            id="research-shared-inspector"
            className="research-inspector"
            aria-label="研究共用右侧面板"
            hidden={!activePanel && state.central_view !== "configuration"}
          >
            <div className="research-inspector-heading">
              <h2 ref={panelHeading} tabIndex={-1}>
                {activePanel?.kind === "step"
                  ? researchSteps.find((step) => step.id === activePanel.step)
                      ?.title
                  : activePanel?.kind === "style"
                    ? "图层样式"
                    : activePanel?.kind === "pixel"
                      ? "原生点查"
                      : state.central_view === "configuration"
                        ? "分析配置"
                        : "图层详情"}
              </h2>
              <button
                type="button"
                className="secondary"
                aria-label="关闭右侧面板"
                onClick={() => {
                  closePanel();
                  if (state.central_view === "configuration")
                    void context
                      .save({
                        ...state,
                        central_view: state.viewed_job_id ? "result" : "map",
                      })
                      .catch(setFailure);
                }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="research-inspector-scroll">
              <div ref={setInspectorHost} />
              {activePanel?.kind === "step" &&
              activePanel.step === "spatial" &&
              activePanel.scope === "draft" ? (
                <details>
                  <summary>空间工具 · 数据质量</summary>
                  <button
                    type="button"
                    className="secondary"
                    disabled={!task.data || busy || !state.inspected_asset_id}
                    onClick={() => void perform(quality, true)}
                  >
                    有效覆盖
                  </button>
                  <p>记录当前研究的处理节点；不代表综合评价。</p>
                </details>
              ) : null}
              {task.data && activePanel?.kind === "step" ? (
                <ResearchStepPanel
                  key={task.data.id}
                  step={activePanel.step}
                  scope={activePanel.scope}
                  task={task.data}
                  assets={assets.data ?? []}
                  job={currentJob.data}
                  result={result.data?.data}
                  onScope={(scope) => setActivePanel({ ...activePanel, scope })}
                  onAdd={
                    canEdit
                      ? () =>
                          void controller.current
                            ?.openAdd("library")
                            .catch(setFailure)
                      : undefined
                  }
                  onInspect={(id) => void inspect(id).catch(setFailure)}
                  review={configurationReview}
                  onRepair={(issue) => {
                    if (issue.action === "inputs")
                      void controller.current
                        ?.openAdd("library")
                        .catch(setFailure);
                    else if (issue.action === "methods") {
                      closePanel();
                      navigate("/methods?project=" + project);
                    } else if (issue.action === "asset" && issue.asset_id)
                      void inspect(issue.asset_id).catch(setFailure);
                    else if (issue.action === "lifecycle") {
                      closePanel();
                      navigate("/tasks?project=" + project);
                    } else
                      openPanel({
                        kind: "step",
                        step: "indicators",
                        scope: "draft",
                      });
                  }}
                />
              ) : null}
              <div
                className="research-step-editor"
                data-step={
                  activePanel?.kind === "step" ? activePanel.step : "indicators"
                }
                hidden={
                  state.central_view !== "configuration" &&
                  (activePanel?.kind !== "step" ||
                    activePanel.scope !== "draft")
                }
              >
                {state.central_view !== "configuration" &&
                activePanel?.kind === "step" &&
                activePanel.step === "indicators" &&
                !!task.data?.draft.mapping.length ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      void context
                        .save({ ...state, central_view: "configuration" })
                        .catch(setFailure)
                    }
                  >
                    展开编辑区
                  </button>
                ) : null}
                {state.central_view === "configuration" ? (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      void context
                        .save({
                          ...state,
                          central_view: state.viewed_job_id ? "result" : "map",
                        })
                        .catch(setFailure)
                    }
                  >
                    恢复面板
                  </button>
                ) : null}
                {task.data ? (
                  <ResearchEditor
                    key={task.data.id}
                    initial={task.data}
                    canEdit={canEdit}
                    step={
                      activePanel?.kind === "step" &&
                      activePanel.scope === "draft"
                        ? activePanel.step
                        : state.central_view === "configuration"
                          ? "indicators"
                          : null
                    }
                    onRun={(job) => {
                      void context
                        .save({
                          ...state,
                          viewed_job_id: job.id,
                          central_view: "result",
                        })
                        .catch(setFailure);
                      void cache.invalidateQueries({
                        queryKey: ["jobs", task.data!.id],
                      });
                    }}
                    onExecute={() => void perform(execute, true)}
                    onPreview={async (assetId, taskId) => {
                      if (currentTask.current?.id !== taskId) return;
                      await view.save(initialDisplay(assetId));
                      if (currentTask.current?.id !== taskId) return;
                      await context.save({...currentResearch.current, inspected_asset_id:assetId,central_view:"map"});
                    }}
                    onController={onController}
                    onDraftSummary={setDraftSummary}
                  />
                ) : null}
              </div>
            </div>
          </aside>
          {task.data ? (
            <nav className="research-flow-rail" aria-label="研究环节">
              {researchSteps.map((step, index) => {
                const current =
                  activePanel?.kind === "step" && activePanel.step === step.id;
                const status = stepStatus(
                  step.id,
                  "draft",
                  task.data!,
                  currentJob.data,
                  result.data?.data,
                );
                return (
                  <button
                    key={step.id}
                    type="button"
                    className="secondary"
                    aria-current={current ? "step" : undefined}
                    aria-label={`${step.title} · ${status.label}${current ? " · 当前查看" : ""}`}
                    aria-controls="research-shared-inspector"
                    onClick={(event) => {
                      openPanel(
                        { kind: "step", step: step.id, scope: "draft" },
                        event.currentTarget,
                      );
                      if (state.central_view === "configuration")
                        void context
                          .save({
                            ...state,
                            central_view: state.viewed_job_id
                              ? "result"
                              : "map",
                          })
                          .catch(setFailure);
                    }}
                  >
                    <span className="flow-step-status">
                      <span>{index + 1}</span>
                      <CircleHelp size={13} aria-hidden="true" />
                    </span>
                    <span>{step.label}</span>
                    <span className="flow-step-tooltip" role="tooltip">
                      {step.title}：{status.label}。{status.note}
                    </span>
                  </button>
                );
              })}
            </nav>
          ) : null}
        </div>
        <CatalogDock
          open={management}
          maximized={state.drawer === "maximized"}
          height={state.dock_heights?.[panel]}
          title="目录管理 · 当前研究保留"
          onHeight={(height) =>
            void context
              .save({
                ...state,
                dock_heights: { ...state.dock_heights, [panel]: height },
              })
              .catch(setFailure)
          }
          onMaximize={() =>
            void context
              .save({
                ...state,
                drawer: state.drawer === "maximized" ? "open" : "maximized",
              })
              .catch(setFailure)
          }
          onClose={() => {
            navigate("/research?project=" + project);
            requestAnimationFrame(() =>
              document
                .querySelector<HTMLAnchorElement>('a[href^="/research"]')
                ?.focus(),
            );
          }}
        >
          {!hidden && (panel === "objectives" || panel === "constraints" || panel === "decisions") ? <PlanningDirectory key={project+panel} project={project} kind={panel} onApply={canEdit && task.data && taskType(task.data)==="planning" ? applyPlanning : undefined}/> : null}
          {panel === "models" && !hidden ? <ModelDirectory project={project}/> : null}
          {panel === "matching" && !hidden ? <MatchingDirectory project={project}/> : null}
          {panel === "planning" && !hidden ? <ManagedCatalog kind="tasks" project={project} fixedStatus="optimization" title="规划任务" onNew={()=>{setNewTaskType("planning");setCreating(true);}} onOpen={r=>navigate("/tasks/"+r.id)}/> : null}
          {panel === "indicators" && !hidden ? <IndicatorDirectory project={project} onUse={task.data?()=>{navigate("/tasks/"+task.data!.id+"?project="+project);openPanel({kind:"step",step:"indicators",scope:"draft"});}:undefined}/> : null}
          <div hidden={panel !== "data"}>
            <Catalog
              project={project}
              canEdit={canEdit}
              directoryOnly
              onInspect={inspect}
              attachedIds={
                task.data?.draft.selection.map((ref) => ref.asset_id) ?? []
              }
              onAdd={async (id) => {
                setFailure(null);
                try {
                  await bind(id);
                } catch (error) {
                  setAttachmentMessage("");
                  setFailure(error);
                  throw error;
                }
              }}
            />
          </div>
          <div hidden={panel !== "tasks"}>
            <ManagedCatalog
              active={panel === "tasks" && !hidden}
              kind="tasks"
              project={project}
              onNew={() => setCreating(true)}
              onOpen={(r) => navigate("/tasks/" + r.id)}
              extraActions={(r) => (
                <button
                  className="secondary"
                  onClick={() =>
                    void perform(async () => {
                      await api(
                        `/management/catalog/tasks/${r.id}/copy`,
                        taskSchema,
                        { method: "POST" },
                      );
                      await cache.invalidateQueries({
                        queryKey: ["managed-catalog", "tasks"],
                      });
                    })
                  }
                >
                  复制
                </button>
              )}
            />
          </div>
          <div hidden={panel !== "methods"}>
            <MethodCatalog
              editorHost={methodEditorHost}
              onEditing={setMethodEditing}
              active={panel === "methods" && !hidden}
              project={project}
              canEdit={canEdit}
              onOpen={(row) => {
                closePanel();
                setMethod(row);
              }}
            />
          </div>
          <div hidden={panel !== "runs"}>
            <ManagedCatalog
              active={panel === "runs" && !hidden}
              kind="runs"
              project={project}
              onOpen={(r) => void perform(() => showRun(r))}
            />
          </div>
          <div hidden={panel !== "results"}>
            <ManagedCatalog
              active={panel === "results" && !hidden}
              kind="results"
              project={project}
              onOpen={(r) => void perform(() => showRun(r))}
            />
          </div>
        </CatalogDock>
        {attachmentMessage ? (
          <p className="attachment-feedback" role="status">
            {attachmentMessage}
          </p>
        ) : null}
        {pendingInput ? (
          <Modal title="选择加入的研究" close={() => setPendingInput(null)}>
            <label>
              目标研究
              <select
                value={targetTask}
                onChange={(event) => setTargetTask(event.target.value)}
              >
                <option value="">请选择研究</option>
                {attachTargets.data?.items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <ErrorNotice error={attachTargets.error ?? failure} />
            <button
              disabled={!targetTask || busy}
              onClick={() =>
                void perform(async () =>
                  bind(
                    pendingInput,
                    await api(`/tasks/${targetTask}`, taskSchema),
                  ),
                )
              }
            >
              加入所选研究
            </button>
            <button className="secondary" onClick={() => setCreating(true)}>
              新建研究并加入
            </button>
          </Modal>
        ) : null}
        {method ? (
          <Modal title="方法版本详情" close={() => setMethod(null)}>
            <h3>
              {method.name} · v{String(method.source_revision)}
            </h3>
            <p>{String(method.basis)}</p>
            <p>
              仅浏览不会改变当前研究。应用后重新核查受影响步骤，既有成果保留。
            </p>
            <button
              disabled={busy || !method.approved || !canEdit}
              onClick={() => void perform(applyMethod, !!task.data)}
            >
              {task.data ? "应用到当前任务" : "以此方法新建任务"}
            </button>
            <ErrorNotice error={failure} />
          </Modal>
        ) : null}
        {creating ? (
          <Modal title="新建研究任务" close={() => setCreating(false)}>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void perform(async () => {
                  const next = await api("/tasks", taskSchema, {
                    method: "POST",
                    body: JSON.stringify({
                      project_id: project,
                      title:
                        title.trim() ||
                        `${taskTypes.find((type) => type.id === newTaskType)?.label ?? "研究"} · ${new Date().toLocaleDateString()}`,
                      task_type: newTaskType,
                    }),
                  });
                  if (pendingInput) await bind(pendingInput, next);
                  setCreating(false);
                  navigate("/tasks/" + next.id);
                  await cache.invalidateQueries({
                    queryKey: ["managed-catalog", "tasks"],
                  });
                });
              }}
            >
              <label>任务类型<select value={newTaskType} onChange={e=>setNewTaskType(e.target.value as TaskType)}>{taskTypes.map(type=><option key={type.id} value={type.id}>{type.label}</option>)}</select></label>
              {newTaskType === "simulation" ? <p>模拟任务可保存和装配资料；动态模型运行服务尚未接通，当前不能提交模拟计算。</p>:null}
              <label>
                任务名称（可选）
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="按用途自动建议"
                />
              </label>
              <ErrorNotice error={failure} />
              <button disabled={busy}>创建并继续</button>
            </form>
          </Modal>
        ) : null}
      </div>
    </ResearchPanelProvider>
  );
}
