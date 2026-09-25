import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { taskSchema } from "./draft";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema } from "./api";
import { AssetViewer } from "./AssetViewer";
import { ErrorNotice } from "./shared";
import { CatalogUpload } from "./CatalogUpload";
import { useCatalogSearch } from "./catalogSearch";
import {
  MetadataEditor,
  CatalogOperation,
  type CatalogSelection,
} from "./CatalogActions";
import {
  initialDisplay,
  useViewState,
  type DisplayState,
} from "./useViewState";
const pageSchema = z.object({
  items: z.array(
    assetSchema.extend({
      display_name: z.string(),
      metadata_revision: z.number(),
      catalog_state: z.string(),
    }),
  ),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
});
export function Catalog({
  project,
  canEdit,
  directoryOnly = false,
  onInspect,
  onAdd,
  attachedIds = [],
}: {
  project: string;
  canEdit: boolean;
  directoryOnly?: boolean;
  onInspect?: (id: string) => Promise<void>;
  onAdd?: (id: string) => Promise<void>;
  attachedIds?: string[];
}) {
  const [adding, setAdding] = useState<string | null>(null);
  const [addError, setAddError] = useState<unknown>(null);
  const cache = useQueryClient();
  const navigate = useNavigate();
  const spatialIntent = useRef(crypto.randomUUID());
  const [spatialBusy, setSpatialBusy] = useState(false),
    [spatialError, setSpatialError] = useState<unknown>(null);
  const [mobileTab, setMobileTab] = useState("map");
  const search = useCatalogSearch();
  const query = search.query;
  const [catalogState, setCatalogState] = useState("active"),
    [profile, setProfile] = useState("");
  const [selected, setSelected] = useState<string[]>([]),
    [editor, setEditor] = useState<string | null>(null);
  const [operation, setOperation] = useState<{
    action: "recycle" | "restore";
    selection: CatalogSelection;
  } | null>(null);
  const [sort, setSort] = useState("newest"),
    [offset, setOffset] = useState(0);
  const view = useViewState(`/projects/${project}/view-state`);
  const { active, saving, error } = view;
  const save = (state: DisplayState) => {
    setMobileTab("map");
    if (onInspect && state.asset_id) return onInspect(state.asset_id);
    return view.save(state);
  };
  const listing = useQuery({
    queryKey: ["catalog", project, query, sort, offset, catalogState, profile],
    queryFn: () =>
      api(
        `/projects/${project}/catalog?${new URLSearchParams({ query, sort, offset: String(offset), state: catalogState, profile })}`,
        pageSchema,
      ),
  });
  const detail = useQuery({
    queryKey: ["asset", active?.asset_id],
    enabled: !!active?.asset_id,
    queryFn: () => api(`/assets/${active!.asset_id}`, assetSchema),
  });
  async function refresh() {
    await cache.invalidateQueries({ queryKey: ["catalog", project] });
    await cache.invalidateQueries({ queryKey: ["assets", project] });
    await cache.invalidateQueries({ queryKey: ["asset-metadata"] });
  }
  return (
    <div
      className={
        directoryOnly ? "catalog-workspace directory-mode" : "catalog-workspace"
      }
    >
      <ErrorNotice
        error={addError ?? error ?? listing.error ?? detail.error ?? spatialError}
      />
      {editor ? (
        <MetadataEditor
          assetId={editor}
          onClose={() => setEditor(null)}
          onSaved={refresh}
        />
      ) : null}
      {operation ? (
        <CatalogOperation
          project={project}
          {...operation}
          onClose={() => {
            setOperation(null);
            setSelected([]);
          }}
          onSaved={refresh}
        />
      ) : null}
      <div
        className="catalog-mobile-tabs"
        role="group"
        aria-label="资料工作区切换"
      >
        <button
          type="button"
          className={mobileTab === "list" ? "" : "secondary"}
          aria-pressed={mobileTab === "list"}
          onClick={() => setMobileTab("list")}
        >
          资料目录
        </button>
        <button
          type="button"
          className={mobileTab === "map" ? "" : "secondary"}
          aria-pressed={mobileTab === "map"}
          onClick={() => setMobileTab("map")}
        >
          地图与详情
        </button>
      </div>
      <div className="catalog-layout" data-mobile-tab={mobileTab}>
        <section className="catalog-list" aria-label="资料目录">
          <div className="catalog-toolbar catalog-single-toolbar">
            <h2>数据资源 <small>{listing.data?.total ?? "…"}</small></h2>
            <input id="catalog-search" aria-label="查找资料" type="search" placeholder="搜索名称、标签、说明" value={search.text}
              onCompositionStart={()=>search.compose(true)} onCompositionEnd={()=>search.compose(false)}
              onKeyDown={event=>{if(event.key==="Enter"){search.submit();setOffset(0);}}}
              onChange={event=>{search.change(event.target.value);setOffset(0);setSelected([]);}} />
            <select aria-label="分类" value={profile} onChange={event=>{setProfile(event.target.value);setOffset(0);setSelected([]);}}>
              <option value="">全部类型</option>{["geotiff","cog","geopackage","shapefile","geojson","csv","csvw","netcdf"].map(value=><option key={value} value={value}>{value.toUpperCase()}</option>)}
            </select>
            <select aria-label="范围" value={catalogState} onChange={event=>{setCatalogState(event.target.value);setOffset(0);setSelected([]);}}>
              <option value="active">已导入资料</option><option value="recycled">已回收资料</option>
            </select>
            <details className="catalog-more"><summary>更多</summary><div>
              <label htmlFor="catalog-sort">排序<select id="catalog-sort" value={sort} onChange={event=>{setSort(event.target.value);setOffset(0);}}><option value="newest">最近接入</option><option value="name">名称</option><option value="size">文件大小</option></select></label>
            </div></details>
            <button type="button" className="secondary" onClick={()=>void refresh()}>刷新</button>
            <CatalogUpload
          project={project}
          disabled={!canEdit || !view.ready}
          onAsset={async (asset, activate) => {
            cache.setQueryData(["asset", asset.id], asset);
            if (activate) await save(initialDisplay(asset.id)).catch(() => {});
            await cache.invalidateQueries({ queryKey: ["catalog", project] });
            await cache.invalidateQueries({ queryKey: ["assets", project] });
          }}
        />
          </div>
          {canEdit ? (
            <div className="catalog-bulk" aria-label="目录批量操作">
              <span>已选 {selected.length} 项</span>
              <button
                type="button"
                className="text-button"
                disabled={!selected.length}
                onClick={() => setSelected([])}
              >
                清除
              </button>
              <button
                type="button"
                className="secondary"
                disabled={!selected.length}
                onClick={() =>
                  setOperation({
                    action: catalogState === "active" ? "recycle" : "restore",
                    selection: { ids: selected },
                  })
                }
              >
                {catalogState === "active" ? "回收所选" : "恢复所选"}
              </button>
              <button
                type="button"
                className="text-button"
                disabled={!listing.data?.total}
                onClick={() =>
                  setOperation({
                    action: catalogState === "active" ? "recycle" : "restore",
                    selection: {
                      query: { query, sort, state: catalogState, profile },
                      excluded_ids: [],
                    },
                  })
                }
              >
                {catalogState === "active" ? "回收筛选全部" : "恢复筛选全部"}
              </button>
            </div>
          ) : null}
          {listing.isPending ? (
            <p role="status">正在读取目录…</p>
          ) : listing.error ? (
            <p role="alert">
              目录读取失败，请重试。
              <button type="button" onClick={() => void listing.refetch()}>
                重新读取
              </button>
            </p>
          ) : !listing.data?.items.length ? (
            <p>{query ? "没有匹配的资料" : "暂无资料，可直接导入查看。"}</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    {canEdit ? <th className="catalog-select"><input type="checkbox" aria-label="全选本页" checked={!!listing.data?.items.length && listing.data.items.every(asset=>selected.includes(asset.id))} onChange={event=>setSelected(event.target.checked ? [...new Set([...selected,...(listing.data?.items.map(asset=>asset.id)??[])])] : selected.filter(id=>!listing.data?.items.some(asset=>asset.id===id)))}/></th> : null}
                    <th>名称 / 类型</th>
                    {onAdd ? <th>任务输入</th> : null}
                    <th className="numeric">大小</th>
                  </tr>
                </thead>
                <tbody>
                  {listing.data.items.map((asset) => (
                    <tr
                      key={asset.id}
                      aria-selected={active?.asset_id === asset.id}
                    >
                      {canEdit ? (
                        <td>
                          <label className="catalog-checkbox">
                            <input
                              type="checkbox"
                              aria-label={`选择 ${asset.display_name}`}
                              checked={selected.includes(asset.id)}
                              onChange={(e) =>
                                setSelected((ids) =>
                                  e.target.checked
                                    ? [...ids, asset.id]
                                    : ids.filter((id) => id !== asset.id),
                                )
                              }
                            />
                          </label>
                        </td>
                      ) : null}
                      <td><div className="catalog-resource-name">
                        <button
                          title={asset.display_name}
                          type="button"
                          className="text-button catalog-name"
                          onClick={() =>
                            void save(initialDisplay(asset.id)).catch(() => {})
                          }
                        >
                          {asset.display_name}
                        </button>
                        <small>
                          {asset.facts.profile} · 资产版本 {asset.revision}
                        </small>
                        {canEdit && catalogState === "active" ? (
                          <button
                            type="button"
                            className="text-button metadata-edit"
                            aria-label={`修改 ${asset.display_name}`}
                            onClick={() => setEditor(asset.id)}
                          >
                            修改
                          </button>
                        ) : null}
                      </div></td>
                      {onAdd ? (
                        <td>
                          <button
                            type="button"
                            className="secondary"
                            disabled={!canEdit || adding === asset.id || attachedIds.includes(asset.id)}
                            onClick={() => {
                              setAdding(asset.id); setAddError(null);
                              void onAdd(asset.id).catch(setAddError).finally(() => setAdding(null));
                            }}
                          >
                            {adding === asset.id ? "正在加入…" : attachedIds.includes(asset.id) ? "已加入" : "加入当前任务"}
                          </button>
                        </td>
                      ) : null}
                      <td className="numeric">
                        {asset.size < 1024
                          ? `${asset.size} B`
                          : asset.size < 1024 ** 2
                            ? `${(asset.size / 1024).toFixed(1)} KiB`
                            : `${(asset.size / 1024 ** 2).toFixed(2)} MiB`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="pagination">
            <span>
              {listing.data
                ? `${listing.data.total} 项；第 ${Math.floor(offset / 20) + 1} 页`
                : "数量读取中"}
            </span>
            <button
              type="button"
              className="secondary"
              disabled={offset === 0}
              onClick={() => setOffset((v) => Math.max(0, v - 20))}
            >
              上一页
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!listing.data || offset + 20 >= listing.data.total}
              onClick={() => setOffset((v) => v + 20)}
            >
              下一页
            </button>
          </div>
        </section>
        {!directoryOnly ? (
          <section className="catalog-detail">
            <p role="status">
              {saving
                ? "正在保存个人视图…"
                : error
                  ? "视图有未保存更改"
                  : active
                    ? "个人视图已保存"
                    : "选择资料后自动保存查看位置"}
            </p>
            {detail.isFetching && !detail.data ? (
              <p role="status">正在读取原件信息…</p>
            ) : null}
            {error ? (
              <button
                type="button"
                className="secondary"
                onClick={() => void view.restore().catch(() => {})}
              >
                读取服务器视图
              </button>
            ) : null}
            {detail.data && active ? (
              <AssetViewer
                onSpatial={
                  canEdit
                    ? async () => {
                        setSpatialBusy(true);
                        setSpatialError(null);
                        try {
                          const task = await api(
                            `/projects/${project}/spatial-tasks`,
                            taskSchema,
                            {
                              method: "POST",
                              body: JSON.stringify({
                                asset_id: detail.data!.id,
                                band: active!.band,
                                idempotency_key: spatialIntent.current,
                              }),
                            },
                          );
                          navigate(`/tasks/${task.id}`);
                        } catch (e) {
                          setSpatialError(e);
                        } finally {
                          setSpatialBusy(false);
                        }
                      }
                    : undefined
                }
                spatialBusy={spatialBusy}
                asset={detail.data}
                state={active}
                onChange={(state) => void save(state).catch(() => {})}
              />
            ) : (
              <p>导入或选择项目资料，地图与详情在这里打开。无需先创建任务。</p>
            )}
          </section>
        ) : null}
      </div>
    </div>
  );
}
