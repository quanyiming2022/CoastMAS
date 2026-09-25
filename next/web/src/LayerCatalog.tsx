import { useId, useState } from "react";
import { Layers, MoreHorizontal, ArrowUp, ArrowDown } from "lucide-react";
export type LayerItem = {
  id: string;
  name: string;
  kind: string;
  role: string;
  visible: boolean;
};
export const layerRoles: Record<string, string> = {
  planning_units: "单元",
  composite: "成果",
  raw_indicator: "原值",
  indicator: "评分",
  contribution: "贡献",
  quality: "质量",
  result: "结果",
  reference: "参考",
};
export function LayerCatalog({
  items,
  activeId,
  onSelect,
  onVisibility,
  onAction,
  onRemove,
  onOrder,
  available = [],
  onAdd,
}: {
  items: LayerItem[];
  activeId?: string;
  onSelect: (id: string) => void;
  onVisibility: (id: string, visible: boolean) => void;
  onAction: (
    id: string,
    action: "locate" | "style" | "details" | "source" | "download",
    trigger: HTMLElement,
  ) => void;
  onRemove: (ids: string[]) => void;
  onOrder: (ids: string[]) => void;
  available?: LayerItem[];
  onAdd?: (id: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [role, setRole] = useState(""),
    [management, setManagement] = useState(false),
    [collapsed, setCollapsed] = useState(false);
  const [selection, setSelection] = useState<string[]>([]);
  const prefix = useId();
  const shown = items.filter(
    (item) =>
      (!role || item.role === role) &&
      (!query ||
        item.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())),
  );
  const selected = selection.filter((id) =>
    items.some((item) => item.id === id),
  );
  function move(id: string, delta: number) {
    const order = items.map((item) => item.id);
    const from = order.indexOf(id),
      to = from + delta;
    if (to < 0 || to >= order.length) return;
    [order[from], order[to]] = [order[to]!, order[from]!];
    onOrder(order);
  }
  return (
    <div
      className="layer-catalog content-tab-body"
      aria-label="当前研究成果图层组"
    >
      <div className="content-searchbar">
        <input
          type="search"
          aria-label="搜索当前图层"
          placeholder="搜索当前图层"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          aria-label="图层分类"
          value={role}
          onChange={(e) => setRole(e.target.value)}
        >
          <option value="">全部图层</option>
          {[...new Set(items.map((item) => item.role))].map((value) => (
            <option key={value} value={value}>
              {layerRoles[value] ?? value}
            </option>
          ))}
        </select>
      </div>
      <div className="content-layer-tools">
        <span>
          {shown.length} / {items.length} 层
        </span>
        <button
          type="button"
          className="secondary"
          aria-pressed={management}
          onClick={() => setManagement(!management)}
        >
          管理
        </button>
        <button
          type="button"
          className="secondary"
          aria-expanded={!collapsed}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? "展开" : "折叠"}
        </button>
      </div>
      {management ? (
        <div className="layer-bulk">
          <label>
            <input
              type="checkbox"
              aria-label="批选筛选图层"
              checked={
                !!shown.length &&
                shown.every((item) => selected.includes(item.id))
              }
              onChange={(e) =>
                setSelection(
                  e.target.checked
                    ? [
                        ...new Set([
                          ...selection,
                          ...shown.map((item) => item.id),
                        ]),
                      ]
                    : selection.filter(
                        (id) => !shown.some((item) => item.id === id),
                      ),
                )
              }
            />
            筛选结果
          </label>
          <button
            className="secondary"
            type="button"
            disabled={!selected.length}
            onClick={() => {
              onRemove(selected);
              setSelection([]);
            }}
          >
            移出地图 ({selected.length})
          </button>
        </div>
      ) : null}
      <div className="content-scroll" hidden={collapsed}>
        {!shown.length ? (
          <p>
            {items.length
              ? "没有匹配图层；搜索不会改变地图显隐。"
              : "当前地图没有图层。"}
          </p>
        ) : null}
        <ul className="compact-layers">
          {shown.map((item) => (
            <li key={item.id} data-active={item.id === activeId}>
              {management ? (
                <input
                  type="checkbox"
                  aria-label={`批选 ${item.name}`}
                  checked={selected.includes(item.id)}
                  onChange={(e) =>
                    setSelection(
                      e.target.checked
                        ? [...selection, item.id]
                        : selection.filter((id) => id !== item.id),
                    )
                  }
                />
              ) : null}
              <input
                type="checkbox"
                aria-label={`显示 ${item.name}`}
                checked={item.visible}
                onChange={(e) => onVisibility(item.id, e.target.checked)}
              />
              <Layers size={15} aria-hidden="true" />
              <button
                type="button"
                className="text-button layer-name"
                title={`${item.name} · ${item.kind}`}
                aria-current={item.id === activeId ? "true" : undefined}
                onClick={() => onSelect(item.id)}
              >
                {item.name}
              </button>
              <span className="layer-kind" title={item.kind}>
                {layerRoles[item.role] ?? item.kind}
              </span>
              <button
                className="secondary layer-more"
                type="button"
                aria-label={`图层 ${item.name} 更多操作`}
                popoverTarget={prefix + item.id}
              >
                <MoreHorizontal size={15} />
              </button>
              <div
                id={prefix + item.id}
                popover="auto"
                role="dialog"
                aria-label={`${item.name} 图层操作`}
                className="content-menu"
              >
                <strong tabIndex={0}>{item.name}</strong>
                {(
                  [
                    ["locate", "定位"],
                    ["style", "样式"],
                    ["details", "属性"],
                    ["source", "来源"],
                    ["download", "下载"],
                  ] as const
                ).map(([action, label]) => (
                  <button
                    type="button"
                    className="secondary"
                    key={action}
                    popoverTarget={prefix + item.id}
                    popoverTargetAction="hide"
                    onClick={(event) =>
                      onAction(item.id, action, event.currentTarget)
                    }
                  >
                    {label}
                  </button>
                ))}
                <button
                  type="button"
                  className="secondary"
                  popoverTarget={prefix + item.id}
                  popoverTargetAction="hide"
                  onClick={() => onRemove([item.id])}
                >
                  移出地图
                </button>
                {management ? (
                  <>
                    <button
                      type="button"
                      className="secondary"
                      disabled={items[0]?.id === item.id}
                      onClick={() => move(item.id, -1)}
                    >
                      <ArrowUp size={15} />
                      上移图层
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={items.at(-1)?.id === item.id}
                      onClick={() => move(item.id, 1)}
                    >
                      <ArrowDown size={15} />
                      下移图层
                    </button>
                  </>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
        {available.length ? (
          <details>
            <summary>添加可用成果图层 ({available.length})</summary>
            {available.map((item) => (
              <button
                className="secondary"
                type="button"
                key={item.id}
                onClick={() => onAdd?.(item.id)}
              >
                {item.name}
              </button>
            ))}
          </details>
        ) : null}
      </div>
    </div>
  );
}
