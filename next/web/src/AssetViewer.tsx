import { lazy, Suspense, type Ref } from "react";
import { api, type Asset } from "./api";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { ErrorNotice } from "./shared";
import { AssetFacts } from "./AssetFacts";
import type { DisplayState } from "./useViewState";
import type { MapControls } from "./AssetMap";
const AssetMap = lazy(() => import("./AssetMap"));
export function AssetViewer({
  asset,
  state,
  onChange,
  onSpatial,
  spatialBusy,
  controls,
}: {
  asset: Asset;
  controls?: Ref<MapControls>;
  onSpatial?: () => Promise<void>;
  spatialBusy?: boolean;
  state: DisplayState;
  onChange: (state: DisplayState) => void;
}) {
  const metadata = useQuery({
    queryKey: ["asset-metadata", asset.id],
    queryFn: () =>
      api(
        `/assets/${asset.id}/metadata`,
        z.object({ display_name: z.string() }),
      ),
  });
  const displayName = metadata.data?.display_name ?? asset.name;
  const raster = ["geotiff", "cog"].includes(asset.facts.profile);
  return (
    <section className="asset-inspector" aria-label="资料查看工作区">
      <div className="viewer-heading">
        <h2 title={asset.name}>{displayName}</h2>
        <ErrorNotice error={metadata.error} />
        <div className="section-heading">
          <span>
            {asset.facts.profile} · 原件已受管 · 资产版本 {asset.revision}
          </span>
          {raster && onSpatial ? (
            <button
              type="button"
              className="secondary"
              disabled={spatialBusy}
              onClick={() => void onSpatial()}
            >
              生成有效覆盖
            </button>
          ) : null}
          <a href={`/api/assets/${asset.id}/download`} download>
            下载原始资料
          </a>
        </div>
      </div>
      {raster ? (
        <>
          {asset.facts.layers[0]!.fields.length > 1 ? (
            <label>
              显示波段
              <select
                value={state.band}
                onChange={(e) =>
                  onChange({ ...state, band: Number(e.target.value) })
                }
              >
                {asset.facts.layers[0]!.fields.map((field, i) => (
                  <option key={field.name} value={i + 1}>
                    {field.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <Suspense fallback={<p role="status">正在加载地图…</p>}>
            <AssetMap
              key={`${asset.id}:${state.band}`}
              legendVisible={state.legend_visible ?? false}
              layerTitle={displayName}
              controls={controls}
              assetId={asset.id}
              band={state.band}
              camera={state.camera}
              visible={state.visible}
              opacity={state.opacity}
              onCamera={(camera) => onChange({ ...state, camera })}
              onDisplay={(change) => onChange({ ...state, ...change })}
            />
          </Suspense>
        </>
      ) : null}
      {raster ? (
        <details className="viewer-file-facts">
          <summary>文件事实与质量信息</summary>
          <AssetFacts asset={asset} expanded />
        </details>
      ) : (
        <AssetFacts asset={asset} expanded />
      )}
    </section>
  );
}
