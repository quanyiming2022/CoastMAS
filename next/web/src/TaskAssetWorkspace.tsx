import { useEffect } from "react";
import type { Asset } from "./api";
import { AssetViewer } from "./AssetViewer";
import { ErrorNotice } from "./shared";
import { initialDisplay, useViewState } from "./useViewState";
export function TaskAssetWorkspace({
  taskId,
  assets,
}: {
  taskId: string;
  assets: Asset[];
}) {
  const view = useViewState(`/tasks/${taskId}/view-state`);
  const { ready, active, save } = view;
  useEffect(() => {
    if (ready && !active?.asset_id && assets[0])
      void save(initialDisplay(assets[0].id)).catch(() => {});
  }, [ready, active?.asset_id, assets, save]);
  const selected = assets.find((asset) => asset.id === active?.asset_id);
  return (
    <section className="task-asset-workspace" aria-label="任务资料工作区">
      <div className="section-heading">
        <h2>资料与地图</h2>
        <p role="status">
          {view.saving
            ? "正在保存个人视图…"
            : view.error
              ? "视图有未保存更改"
              : active
                ? "个人视图已保存"
                : "接入资料后自动打开"}
        </p>
      </div>
      <ErrorNotice error={view.error} />
      {view.error ? (
        <button
          type="button"
          className="secondary"
          onClick={() => void view.restore().catch(() => {})}
        >
          读取服务器视图
        </button>
      ) : null}
      <div className="task-asset-layout">
        <nav aria-label="任务资料列表">
          <ul>
            {assets.map((asset) => (
              <li key={asset.id}>
                <button
                  type="button"
                  className={selected?.id === asset.id ? "" : "secondary"}
                  aria-current={selected?.id === asset.id ? "true" : undefined}
                  onClick={() =>
                    void save(initialDisplay(asset.id)).catch(() => {})
                  }
                >
                  {asset.name}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        {selected && active ? (
          <AssetViewer
            asset={selected}
            state={active}
            onChange={(state) => void save(state).catch(() => {})}
          />
        ) : (
          <p>
            {assets.length
              ? "正在读取个人视图…"
              : "文件接入后自动显示，不需要先补充科学定义或选择方法。"}
          </p>
        )}
      </div>
    </section>
  );
}
