import { Layers3, FolderOpen, MapPinned, Clock3, ChartNoAxesCombined, SlidersHorizontal, Network, FlaskConical, Settings2, type LucideIcon } from "lucide-react";

// Product architecture, not a registry of technical infrastructure.
export const v3Centers = [
  { id: "workspace", label: "工作台" },
  { id: "research", label: "项目与研究" },
  { id: "data", label: "数据" },
  { id: "methods", label: "指标与方法" },
  { id: "modelops", label: "模型工程" },
  { id: "coupling", label: "耦合与工作流" },
  { id: "planning", label: "规划与优化" },
  { id: "runs", label: "运行" },
  { id: "results", label: "成果" },
  { id: "management", label: "管理" },
] as const;
export type CenterId = (typeof v3Centers)[number]["id"];
export type NavigationItem = {
  id: string; group: CenterId; label: string; short: string;
  path?: string; icon: LucideIcon; manage?: boolean; systemOnly?: boolean;
  status?: "development";
};
const items = (group: CenterId, icon: LucideIcon, entries: [string,string,string?][], permission?: "manage" | "systemOnly"): NavigationItem[] => entries.map(([id,label,path]) => ({
  id, group, label, short:label.slice(0,2), path, icon,
  ...(!path ? {status:"development" as const} : {}),
  ...(permission ? {[permission]:true} : {}),
}));
export const navigation: NavigationItem[] = [
  ...items("workspace", Layers3, [["workspace","工作台","/research"]]),
  ...items("research", FolderOpen, [["projects","项目","/projects"],["topics","研究内容"],["tasks","研究任务","/tasks"],["relations","任务关系"]]),
  ...items("data", MapPinned, [["data","数据资源","/library"],["import","数据导入"],["processing","数据处理"],["quality","数据质量"]]),
  ...items("methods", FlaskConical, [["indicators","指标库","/indicators"],["scoring","标准化方法"],["weighting","权重方法"],["methods","综合评价方法","/methods"],["classification","分级方法"],["analysis-methods","时空分析方法"]]),
  ...items("modelops", FlaskConical, [["models","模型目录","/models"],["model-intake","模型接入"],["model-decomposition","模型解构"],["model-contracts","模型契约"],["model-tests","模型测试"],["environments","运行环境"],["releases","模型版本"]]),
  ...items("coupling", Network, [["matching","数据—模型匹配","/coupling/matching"],["couplings","模型—模型耦合"],["adapters","数据适配"],["scene-constraints","场景约束"],["workflows","工作流"],["orchestration","服务编排"]]),
  ...items("planning", MapPinned, [["planning","规划任务","/planning/tasks"],["objectives","规划目标","/planning/objectives"],["constraints","约束库","/planning/constraints"],["variables","决策变量","/planning/decisions"],["scenarios","情景方案"],["solvers","优化求解器"],["planning-comparison","方案比较"]]),
  ...items("runs", Clock3, [["current-runs","当前运行"],["queue","运行队列"],["runs","运行记录","/runs"],["compute","计算资源"],["diagnostics","问题诊断"]]),
  ...items("results", ChartNoAxesCombined, [["map-results","地图成果"],["results","数据成果","/results"],["simulation-results","模拟成果"],["planning-results","规划成果"],["analysis-results","时空分析"],["result-comparison","方案比较"],["reports","报告"],["publishing","服务发布"]]),
  ...items("management", Settings2, [["users","用户与权限","/management/users"]],"systemOnly"),
  ...items("management", Network, [["members","项目成员"],["extensions","扩展管理"]],"manage"),
  ...items("management", SlidersHorizontal, [["settings","系统设置","/management/settings"]],"systemOnly"),
  ...items("management", Clock3, [["audit","审计","/management/audit"],["recycle","回收站"]],"manage"),
];
export function visibleNavigation(canManage: boolean, systemAdmin = canManage, development = import.meta.env.VITE_COASTMAS_DEVELOPMENT === "true") {
  return navigation.filter(item => (!item.manage || canManage) && (!item.systemOnly || systemAdmin) && (!item.status || development));
}
export function navigationURL(item: NavigationItem, project: string) {
  if (!item.path) throw new Error("尚未实现的入口没有可导航路由");
  const query = new URLSearchParams();
  if (project) query.set("project",project);
  return item.path + (query.size ? "?"+query.toString() : "");
}
export function activeNavigation(path: string, _search: string, taskPurpose: string | null) {
  if (/^\/tasks\/[^/]+$/.test(path)) return taskPurpose === "method" ? "methods" : "workspace";
  if (path === "/") return "tasks";
  return navigation.find(item => item.path === path)?.id ?? null;
}
