import { matchPath } from "react-router-dom";
import {
  LayoutDashboard,
  Map,
  Database,
  MapPin,
  Clock,
  WandSparkles,
  Workflow,
  Boxes,
  Network,
  Play,
  ChartColumn,
  ListChecks,
  Grid2X2,
  Users,
  FlaskConical,
  Settings,
  type LucideIcon,
} from "lucide-react";

export type GroupId = "data" | "models" | "results" | "assessment";
export const groups: { id: GroupId; label: string }[] = [
  { id: "data", label: "场景与数据" },
  { id: "models", label: "模型与编排" },
  { id: "results", label: "运行与成果" },
  { id: "assessment", label: "评价与协同" },
];
interface NavigationEntry {
  id: string;
  label: string;
  path: string;
  matches: string[];
  icon: LucideIcon;
  group: GroupId | null;
  permission: "authenticated" | "admin";
}
// Existing routes remain the source of destinations; aliases assign child tools to their parent.
export const navigation: NavigationEntry[] = [
  {
    id: "dashboard",
    label: "项目概览",
    path: "/dashboard",
    matches: ["/dashboard"],
    icon: LayoutDashboard,
    group: "data",
    permission: "authenticated",
  },
  {
    id: "scenes",
    label: "场景空间",
    path: "/scenes",
    matches: ["/scenes/*"],
    icon: Map,
    group: "data",
    permission: "authenticated",
  },
  {
    id: "data",
    label: "数据目录",
    path: "/data",
    matches: ["/data/*", "/data-sources/*"],
    icon: Database,
    group: "data",
    permission: "authenticated",
  },
  {
    id: "entities",
    label: "地理实体",
    path: "/entities",
    matches: ["/entities"],
    icon: MapPin,
    group: "data",
    permission: "authenticated",
  },
  {
    id: "temporal",
    label: "时间适配",
    path: "/temporal",
    matches: ["/temporal"],
    icon: Clock,
    group: "data",
    permission: "authenticated",
  },
  {
    id: "planner",
    label: "智能编排",
    path: "/planner",
    matches: ["/planner"],
    icon: WandSparkles,
    group: "models",
    permission: "authenticated",
  },
  {
    id: "workflows",
    label: "工作流",
    path: "/workflows",
    matches: ["/workflows/*"],
    icon: Workflow,
    group: "models",
    permission: "authenticated",
  },
  {
    id: "models",
    label: "模型中心",
    path: "/models",
    matches: ["/models/*"],
    icon: Boxes,
    group: "models",
    permission: "authenticated",
  },
  {
    id: "knowledge",
    label: "知识图谱",
    path: "/knowledge-graph",
    matches: ["/knowledge-graph"],
    icon: Network,
    group: "models",
    permission: "authenticated",
  },
  {
    id: "runs",
    label: "运行中心",
    path: "/runs",
    matches: ["/runs/*"],
    icon: Play,
    group: "results",
    permission: "authenticated",
  },
  {
    id: "results",
    label: "结果中心",
    path: "/results",
    matches: ["/results/*"],
    icon: ChartColumn,
    group: "results",
    permission: "authenticated",
  },
  {
    id: "assessments",
    label: "综合评价",
    path: "/assessments",
    matches: ["/assessments/*", "/assessment-records/*"],
    icon: ListChecks,
    group: "assessment",
    permission: "authenticated",
  },
  {
    id: "optimizations",
    label: "空间优化",
    path: "/optimizations",
    matches: ["/optimizations/*"],
    icon: Grid2X2,
    group: "assessment",
    permission: "authenticated",
  },
  {
    id: "collaboration",
    label: "协同方案",
    path: "/collaboration",
    matches: ["/collaboration"],
    icon: Users,
    group: "assessment",
    permission: "authenticated",
  },
  {
    id: "research",
    label: "科研验证",
    path: "/research",
    matches: ["/research/*"],
    icon: FlaskConical,
    group: null,
    permission: "authenticated",
  },
  {
    id: "admin",
    label: "系统管理",
    path: "/admin",
    matches: ["/admin"],
    icon: Settings,
    group: null,
    permission: "admin",
  },
];
export function activeEntry(pathname: string) {
  return navigation.find((item) =>
    item.matches.some((path) => matchPath({ path, end: true }, pathname)),
  );
}
export type ExpandedGroups = Record<GroupId, boolean>;
export const NAV_STORAGE_KEY = "coastmas.navigation.groups.v1";
export function initialGroups(pathname: string): ExpandedGroups {
  const expanded: ExpandedGroups = {
    data: true,
    models: true,
    results: false,
    assessment: false,
  };
  try {
    const stored: unknown = JSON.parse(
      localStorage.getItem(NAV_STORAGE_KEY) ?? "null",
    );
    if (stored && typeof stored === "object")
      for (const { id } of groups) {
        const value = (stored as Record<string, unknown>)[id];
        if (typeof value === "boolean") expanded[id] = value;
      }
  } catch {
    /* Storage is optional UI convenience, never an authorization source. */
  }
  const group = activeEntry(pathname)?.group;
  if (group) expanded[group] = true;
  return expanded;
}
