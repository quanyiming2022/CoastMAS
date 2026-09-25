import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { api, assetSchema } from "./api";
import { ErrorNotice } from "./shared";
const pageSchema = z.object({ items: z.array(assetSchema), total: z.number() });
export function AssetPicker({
  project,
  selection,
  disabled,
  onSelect,
  initialOpen = false,
}: {
  initialOpen?: boolean;
  project: string;
  selection: string[];
  disabled: boolean;
  onSelect: (id: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(initialOpen),
    [query, setQuery] = useState(""),
    [profile, setProfile] = useState(""),
    [offset, setOffset] = useState(0);
  const listing = useQuery({
    queryKey: ["catalog-picker", project, query, profile, offset],
    enabled: open,
    queryFn: () =>
      api(
        `/projects/${project}/catalog?${new URLSearchParams({ query, profile, offset: String(offset), limit: "20" })}`,
        pageSchema,
      ),
  });
  return (
    <details
      className="disclosure"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>从资料库选择</summary>
      <label>
        查找资料
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOffset(0);
          }}
        />
      </label>
      <label>
        资料类型
        <select
          value={profile}
          onChange={(event) => {
            setProfile(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">全部类型</option>
          {[
            "geotiff",
            "cog",
            "csv",
            "csvw",
            "geojson",
            "gpkg",
            "netcdf",
            "stac",
          ].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <ErrorNotice error={listing.error} />
      {listing.isFetching ? <p role="status">正在读取目录…</p> : null}
      {listing.data?.items.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {listing.data.items.map((asset) => (
                <tr key={asset.id}>
                  <td>{asset.name}</td>
                  <td>{asset.facts.profile}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      disabled={disabled || selection.includes(asset.id)}
                      onClick={() => void onSelect(asset.id)}
                    >
                      {selection.includes(asset.id)
                        ? "已加入研究"
                        : `加入研究 ${asset.name}`}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !listing.isPending && !listing.error ? (
        <p>{query ? "没有匹配的资料" : "暂无可复用资料"}</p>
      ) : null}
      <div className="pagination">
        <span>
          {listing.data
            ? `共 ${listing.data.total} 项；第 ${Math.floor(offset / 20) + 1} 页`
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
    </details>
  );
}
