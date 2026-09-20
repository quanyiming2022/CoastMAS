import { Position, type Edge, type Node } from "@xyflow/react";
import type { ModelDecomposition } from "./generated/contracts";
export const stageLabels = {
  preprocess: "预处理",
  compute: "计算",
  postprocess: "后处理",
  validate: "验证",
};
export function decompositionGraph(result: ModelDecomposition): {
  nodes: Node[];
  edges: Edge[];
} {
  const components = new Map(
    result.components.map((component) => [component.id, component]),
  );
  if (components.size !== result.components.length)
    throw new Error("拆解组件标识重复");
  const incoming = new Map([...components.keys()].map((id) => [id, 0]));
  const children = new Map(
    [...components.keys()].map((id) => [id, [] as string[]]),
  );
  const levels = new Map([...components.keys()].map((id) => [id, 0]));
  for (const [source, target] of result.dependencies) {
    if (!components.has(source) || !components.has(target))
      throw new Error("依赖引用未知组件");
    incoming.set(target, incoming.get(target)! + 1);
    children.get(source)!.push(target);
  }
  const ready = [...incoming]
    .filter(([, count]) => count === 0)
    .map(([id]) => id);
  let visited = 0;
  for (let index = 0; index < ready.length; index++) {
    const current = ready[index]!;
    visited++;
    for (const child of children.get(current)!) {
      levels.set(child, Math.max(levels.get(child)!, levels.get(current)! + 1));
      incoming.set(child, incoming.get(child)! - 1);
      if (incoming.get(child) === 0) ready.push(child);
    }
  }
  if (visited !== components.size) throw new Error("拆解依赖存在循环");
  const rows = new Map<number, number>();
  return {
    nodes: result.components.map((component) => {
      const level = levels.get(component.id)!;
      const row = rows.get(level) ?? 0;
      rows.set(level, row + 1);
      return {
        id: component.id,
        position: { x: level * 290, y: row * 130 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: `${stageLabels[component.stage]} · ${component.id}${component.atomic ? "（原子模型）" : ""}`,
        },
      };
    }),
    edges: result.dependencies.map(([source, target]) => ({
      id: JSON.stringify([source, target]),
      source,
      target,
    })),
  };
}
