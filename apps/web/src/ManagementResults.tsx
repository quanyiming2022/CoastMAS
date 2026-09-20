import { lazy, Suspense, useState } from "react";
import type { GeographicCollection } from "./result-data";
import type { ResultView } from "./generated/contracts";
import { Details, display, Loading, Panel } from "./components";

const GeoMap = lazy(() => import("./GeoMap"));

const statusLabels = {
  BOUND: "全部绑定",
  PARTIAL: "部分绑定",
  UNBOUND: "尚未绑定",
  NOT_APPLICABLE: "无管理单元绑定语义",
};
const metricLabels: Record<string, string> = {
  inundated_area_m2: "受淹面积",
  estimated_population: "估算受影响人口",
  unknown_area_m2: "DEM 未知面积",
  study_area_m2: "研究区内面积",
  population_in_unknown_dem_area: "DEM 未知区域人口",
  fraction: "受淹比例",
  change: "期间变化",
  trend: "年变化趋势",
  ranks: "各期排名",
  scores: "评价分数",
  classes: "评价等级",
  years: "年份",
};
export default function ManagementResults({
  view,
  geometries,
}: {
  view: ResultView;
  geometries?: GeographicCollection;
}) {
  const [selectedEntity, setSelectedEntity] = useState<string | null>(null);
  const mappedEntities = new Set(
    geometries?.features.map((feature) => feature.properties?.entity_id),
  );
  const mapData: GeographicCollection | undefined = geometries
    ? {
        ...geometries,
        features: geometries.features.map((feature) => ({
          ...feature,
          properties: {
            ...feature.properties,
            selected: feature.properties?.entity_id === selectedEntity,
            layer_kind:
              feature.properties?.entity_id === selectedEntity
                ? "aoi"
                : "entity",
          },
        })),
      }
    : undefined;
  function selectMapEntity(properties: Record<string, unknown>) {
    if (
      typeof properties.entity_id === "string" &&
      view.entity_binding.some(
        (binding) =>
          binding.geographic_entity_id === properties.entity_id &&
          binding.geographic_entity_version === properties.entity_version,
      )
    ) {
      setSelectedEntity(properties.entity_id);
    }
  }
  const bindings = new Map(
    view.entity_binding.map((binding) => [binding.result_object_id, binding]),
  );
  return (
    <Panel title="管理结果与地理实体">
      <p>{statusLabels[view.binding_status]}</p>
      <p>
        仅按场景选中实体的管理单元标识精确关联。未绑定的结果仍保留；绑定本身不代表人工审查通过。
      </p>
      {mapData?.features.length ? (
        <>
          <p>点击实体或“定位”可联动结果表。地图显示该次运行保存的实体边界。</p>
          <button className="secondary" onClick={() => setSelectedEntity(null)}>
            显示全部绑定实体
          </button>
          <Suspense fallback={<Loading />}>
            <GeoMap
              data={mapData}
              label="结果绑定实体地图"
              onFeatureClick={selectMapEntity}
            />
          </Suspense>
        </>
      ) : (
        <p>此结果没有可显示的绑定实体几何；不推断未绑定单元的位置。</p>
      )}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>结果对象</th>
              <th>管理单元</th>
              <th>地理实体版本</th>
              <th>指标与单位</th>
            </tr>
          </thead>
          <tbody>
            {view.objects.map((object) => {
              const binding = bindings.get(object.id);
              return (
                <tr
                  key={object.id}
                  data-selected={
                    binding?.geographic_entity_id === selectedEntity
                  }
                >
                  <td>
                    <span className="break">
                      {object.node_id} / {object.variable}
                    </span>
                    <Details
                      title="对象与来源"
                      value={{
                        id: object.id,
                        model: object.model,
                        source_pointer: object.source_pointer,
                      }}
                    />
                  </td>
                  <td>
                    {object.management_unit_id ?? "不适用"}
                    {binding &&
                    mappedEntities.has(binding.geographic_entity_id) ? (
                      <button
                        className="secondary"
                        aria-pressed={
                          selectedEntity === binding.geographic_entity_id
                        }
                        onClick={() =>
                          setSelectedEntity(binding.geographic_entity_id)
                        }
                      >
                        定位 {object.management_unit_id}
                      </button>
                    ) : null}
                  </td>
                  <td>
                    {binding
                      ? `${binding.geographic_entity_id} · v${binding.geographic_entity_version}`
                      : object.management_unit_id
                        ? "未绑定地理实体"
                        : "不适用"}
                  </td>
                  <td>
                    {Object.entries(object.values ?? {}).map(
                      ([name, value]) => (
                        <div key={name}>
                          <span>{metricLabels[name] ?? name}：</span>
                          <span>
                            {display(value)}
                            {object.units?.[name]
                              ? ` ${object.units[name]}`
                              : ""}
                          </span>
                        </div>
                      ),
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
