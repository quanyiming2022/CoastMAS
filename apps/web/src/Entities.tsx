import { lazy, Suspense, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { request, resourceSchema } from "./api";
import { contract } from "./contracts";
import { geographicCollection } from "./result-data";
import { useWorkspace } from "./workspace";
import { ErrorNotice, Loading, PageTitle } from "./components";
import type { GeographicEntity } from "./generated/contracts";
const GeoMap = lazy(() => import("./GeoMap"));
const entityContract = contract("GeographicEntity");
const revision = z.object({
  spec: entityContract,
  version: z.number().int().positive(),
  checksum: z.string(),
});
const spatial = geographicCollection.extend({
  has_more: z.boolean(),
  offset: z.number(),
});
const types: Record<GeographicEntity["type"], string> = {
  coast_segment: "岸段",
  wetland: "湿地",
  land_parcel: "地块",
  administrative_unit: "行政单元",
  management_unit: "管理单元",
  water_body: "水体",
  protection_zone: "保护区",
  custom: "自定义",
};

export default function Entities() {
  const { projectId } = useWorkspace();
  const [selected, setSelected] = useState("");
  const [version, setVersion] = useState("");
  const [offset, setOffset] = useState(0);
  const catalog = useQuery({
    queryKey: ["entities", projectId, offset],
    queryFn: ({ signal }) =>
      request(
        `/entities?project_id=${encodeURIComponent(projectId)}&limit=50&offset=${offset}`,
        z.array(resourceSchema),
        { signal },
      ),
  });
  const current = useQuery({
    queryKey: ["entity", selected, version],
    enabled: !!selected,
    queryFn: ({ signal }) =>
      request(
        `/entities/${encodeURIComponent(selected)}${version ? `?version=${encodeURIComponent(version)}` : ""}`,
        revision,
        { signal },
      ),
  });
  const map = useQuery({
    queryKey: ["entity-map", projectId, offset],
    queryFn: ({ signal }) =>
      request(
        `/entities/spatial?project_id=${encodeURIComponent(projectId)}&west=-180&south=-90&east=180&north=90&limit=50&offset=${offset}`,
        spatial,
        { signal },
      ),
  });
  return (
    <>
      <PageTitle
        title="地理实体"
        description="管理岸段、湿地与管理单元的空间版本。原始坐标系与有效时间随版本保留。"
      />
      <div className="two-columns">
        <section className="panel">
          <h2>实体目录</h2>
          <ErrorNotice error={catalog.error} />
          <button
            onClick={() => {
              setSelected("");
              setVersion("");
            }}
          >
            新建实体
          </button>
          {catalog.isPending ? (
            <Loading />
          ) : (
            <ul>
              {catalog.data?.map((item) => (
                <li key={item.id}>
                  <button
                    className="secondary"
                    onClick={() => {
                      setSelected(item.id);
                      setVersion("");
                    }}
                  >
                    {item.name} · v{item.version}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {!catalog.data?.length && !catalog.isPending && (
            <p>这一页没有实体。</p>
          )}
          <div className="actions">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 50))}
            >
              上一页
            </button>
            <span>第 {offset / 50 + 1} 页</span>
            <button
              disabled={(catalog.data?.length ?? 0) < 50}
              onClick={() => setOffset(offset + 50)}
            >
              下一页
            </button>
          </div>
          {selected && (
            <label>
              读取版本
              <input
                aria-label="读取版本"
                type="number"
                min="1"
                placeholder="留空为当前版本"
                value={version}
                onChange={(event) => setVersion(event.target.value)}
              />
            </label>
          )}
          <ErrorNotice error={current.error} />
        </section>
        <section className="panel">
          <h2>{selected ? "修订实体" : "创建实体"}</h2>
          {selected && current.isPending ? (
            <Loading />
          ) : (
            (!selected || current.data) && (
              <EntityEditor
                key={`${selected}:${current.data?.version ?? 0}`}
                projectId={projectId}
                initial={selected ? current.data?.spec : undefined}
                onSaved={(id) => {
                  setSelected(id);
                  setVersion("");
                }}
              />
            )
          )}
          {current.data && (
            <details>
              <summary>版本来源与属性</summary>
              <p>版本摘要：{current.data.checksum}</p>
              <pre>{JSON.stringify(current.data.spec.properties, null, 2)}</pre>
            </details>
          )}
        </section>
      </div>
      <section className="panel">
        <h2>当前空间版本</h2>
        <ErrorNotice error={map.error} />
        {map.isPending ? (
          <Loading />
        ) : map.data && map.data.features.length > 0 ? (
          <Suspense fallback={<Loading />}>
            <GeoMap data={map.data} label="地理实体地图" />
          </Suspense>
        ) : (
          <p>当前页没有可显示的空间对象。</p>
        )}
        {map.data?.has_more && (
          <p>
            还有更多空间对象，请翻页查看。地图按实体标识排序，每页最多 50 个。
          </p>
        )}
      </section>
    </>
  );
}

function EntityEditor({
  projectId,
  initial,
  onSaved,
}: {
  projectId: string;
  initial?: GeographicEntity;
  onSaved: (id: string) => void;
}) {
  const client = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [type, setType] = useState<GeographicEntity["type"]>(
    initial?.type ?? "management_unit",
  );
  const [crs, setCrs] = useState(initial?.crs ?? "EPSG:4326");
  const [management, setManagement] = useState(
    initial?.management_unit_id ?? "",
  );
  const [start, setStart] = useState(
    initial?.valid_from ?? new Date().toISOString(),
  );
  const [end, setEnd] = useState(initial?.valid_to ?? "");
  const [file, setFile] = useState<File | null>(null);
  const save = useMutation({
    mutationFn: async () => {
      let geometry: unknown = initial?.geometry;
      let properties: unknown = initial?.properties ?? {};
      if (file) {
        if (file.size > 8 * 1024 * 1024)
          throw new Error("几何文件不能超过 8 MB");
        const source: unknown = JSON.parse(await file.text());
        const feature = z
          .object({
            type: z.literal("Feature"),
            geometry: z.unknown(),
            properties: z.record(z.string(), z.unknown()).nullable().optional(),
          })
          .safeParse(source);
        if (feature.success) {
          geometry = feature.data.geometry;
          properties = feature.data.properties ?? {};
        } else geometry = source;
      }
      if (!geometry) throw new Error("请选择单个 GeoJSON 几何或 Feature 文件");
      const spec = entityContract.parse({
        id: initial?.id ?? `entity-${crypto.randomUUID()}`,
        name,
        version: (initial?.version ?? 0) + 1,
        type,
        crs,
        geometry,
        management_unit_id: management.trim() || null,
        valid_from: start,
        valid_to: end || null,
        properties,
      });
      return request(
        initial ? `/entities/${encodeURIComponent(initial.id)}` : "/entities",
        revision,
        {
          method: initial ? "PUT" : "POST",
          body: initial
            ? { expected_version: initial.version, spec }
            : { project_id: projectId, spec },
        },
      );
    },
    onSuccess: async (result) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["entities", projectId] }),
        client.invalidateQueries({ queryKey: ["entity-map", projectId] }),
        client.invalidateQueries({ queryKey: ["entity", result.spec.id] }),
      ]);
      onSaved(result.spec.id);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form className="entity-form" onSubmit={submit}>
      {initial && (
        <p>
          地理实体标识：{initial.id} · 已读取 v{initial.version}
          ；保存将创建下一版本。
        </p>
      )}
      <label>
        实体名称
        <input
          aria-label="实体名称"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label>
        实体类型
        <select
          aria-label="实体类型"
          value={type}
          onChange={(event) =>
            setType(event.target.value as GeographicEntity["type"])
          }
        >
          {Object.entries(types).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        管理单元标识
        <input
          aria-label="管理单元标识"
          required={type === "management_unit"}
          value={management}
          onChange={(event) => setManagement(event.target.value)}
        />
      </label>
      <label>
        源坐标系
        <input
          aria-label="源坐标系"
          required
          value={crs}
          onChange={(event) => setCrs(event.target.value)}
        />
      </label>
      <label>
        生效时间（含时区）
        <input
          aria-label="生效时间"
          required
          value={start}
          onChange={(event) => setStart(event.target.value)}
        />
      </label>
      <label>
        失效时间（可留空）
        <input
          aria-label="失效时间"
          value={end}
          onChange={(event) => setEnd(event.target.value)}
        />
      </label>
      <label>
        几何文件
        <input
          aria-label="几何文件"
          type="file"
          accept=".json,.geojson"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <p className="muted">
        单个 GeoJSON 几何或 Feature；坐标顺序为
        X/Y。修订时未选择文件则保留原几何和属性。时间区间为前闭后开。
      </p>
      <ErrorNotice error={save.error} />
      <button type="submit" disabled={save.isPending}>
        {save.isPending ? "正在保存…" : "保存实体版本"}
      </button>
      {save.isSuccess && <p role="status">实体版本已保存。</p>}
    </form>
  );
}
