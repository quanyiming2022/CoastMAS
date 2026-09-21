# CoastMAS UI 约定

适用于现有科研/GIS工作台；不得改变路由、权限、科学参数、字段提交和任务行为。地图、工作流画布、图表及第三方弹层不套用业务表单/表格样式。

共享尺寸集中在 `apps/web/src/styles.css`：深青侧栏、青色强调、浅灰背景和白色内容区；正文约14px，标题24–28px，区块16–18px；8/16/24px间距，约8px圆角，40px常规控件，44–48px表格行。普通编辑表单最大1120px，短字段双列、窄屏单列，长内容跨列。列表使用标题/操作、可横向滚动表格、独立分页；加载、无数据、筛选无结果和失败分别展示。共享 `DataTable` 覆盖33处表格；原生表单控件使用工作台作用域和统一tokens，滚动容器可用键盘访问。全站回归按实际运行证据更新。

## NAV-01 入口映射

唯一配置 `apps/web/src/navigation.ts`；桌面与手机复用同一渲染和授权结果。

| 原入口 | 新分组 / 名称 | 原路由 |
| --- | --- | --- |
| 项目概览 | 场景与数据 / 项目概览 | /dashboard |
| 场景空间 | 场景与数据 / 场景空间 | /scenes |
| 数据目录 | 场景与数据 / 数据目录 | /data |
| 地理实体 | 场景与数据 / 地理实体 | /entities |
| 时间适配 | 场景与数据 / 时间适配 | /temporal |
| 智能规划 | 模型与编排 / 智能编排 | /planner |
| 工作流 | 模型与编排 / 工作流 | /workflows |
| 模型中心 | 模型与编排 / 模型中心 | /models |
| 知识图谱 | 模型与编排 / 知识图谱 | /knowledge-graph |
| 运行中心 | 运行与成果 / 运行中心 | /runs |
| 结果中心 | 运行与成果 / 结果中心 | /results |
| 评价中心 | 评价与协同 / 综合评价 | /assessments |
| 空间优化 | 评价与协同 / 空间优化 | /optimizations |
| 协同方案 | 评价与协同 / 协同方案 | /collaboration |
| 科研评估 | 独立入口 / 科研验证 | /research |
| 系统管理 | 底部固定区 / 系统管理 | /admin |

数据来源 `/data-sources` 保留数据目录中的原入口，归属数据目录；评价记录 `/assessment-records` 保留综合评价中的原入口，归属综合评价；静态模型拆解 `/models/decompose` 保留模型中心中的原入口，归属模型中心。各编辑、详情、版本页通过 React Router 按路径段匹配所属入口，不重复挂载菜单。模型中心和知识图谱均为已有可用页面。

四组独立开合；首次进入和真实路径变化展开所属组，其余恢复本地布尔偏好。没有已存偏好时默认展开场景与数据、模型与编排；存储失败不阻碍使用。侧栏状态不控制主内容挂载，不新增项目查询或修改 query/hash。权限未加载时不渲染侧栏，系统管理只依据既有 `is_admin`。

桌面240px；品牌、底部管理及账号区固定，中段独立滚动；当前项有浅青背景、加粗和左侧标记。手机用原生模态对话框，支持键盘焦点约束、Esc、选择链接后关闭及焦点返回。长邮箱省略显示并保留完整文本和title。

验收证据保存在 `artifacts/navigation/` 和 `artifacts/ui-consistency/`，运行记录在既有 `artifacts/evidence/`。只有实际浏览器检查和截图审阅通过才记录视觉验收通过。

前端文档分发必须支持资源标识中的点号（例如 `.tif`）；浏览器文档导航与静态资源请求要区分，API未知路径和缺失构建资源仍返回真实错误。NAV覆盖发现此原有缺陷，新增定向用例保护详情刷新、路径越界和静态资源边界；主服务不因UI验收被重启。

## 修改与覆盖索引

导航修改：`App.tsx`、`Sidebar.tsx`、`navigation.ts`；三个入口的页面标题在 `Planner.tsx`、`IndicatorFrameworks.tsx`、`Research.tsx` 同步。共享展示：`components.tsx`、`styles.css`。额外表单展示标记涉及 `Entities.tsx`、`ModelEditor.tsx`、`SceneRun.tsx`。

共享表格调用点（合计33处）：`Admin.tsx`（4）、`AssessmentRecords.tsx`（2）、`AssessmentResults.tsx`（2）、`Catalog.tsx`（1）、`CoastalStatistics.tsx`（1）、`Collaboration.tsx`（3）、`Dashboard.tsx`（1）、`DataSources.tsx`（1）、`DataWorkspace.tsx`（1）、`IndicatorFrameworks.tsx`（1）、`KnowledgeGraph.tsx`（1）、`ManagementResults.tsx`（1）、`ModelDecomposer.tsx`（1）、`Research.tsx`（1）、`ResearchReportView.tsx`（2）、`ResultComparison.tsx`（1）、`Results.tsx`（2）、`Runs.tsx`（1）、`SceneWorkspace.tsx`（1）、`SpatialOptimization.tsx`（4）、`TemporalAdaptation.tsx`（1）。

测试使用现有Vitest/Playwright，所有业务写入、账号与会话实验位于临时数据库、对象桶和队列；主科研数据及API/worker/模型任务不因本轮测试被停止。截图中的合成数据仅为隔离测试夹具，不是三个真实影像demo。

## 本轮验收结果

最终证据 `20260921T085413062004Z-ui-visual-final`：58项前端测试、lint、类型检查、生产构建及24条真实浏览器场景通过。42条页面路径 × 3视口 = 126张全站覆盖截图；代表页与导航另有同尺寸前后图，关键实际截图已人工审阅。导航/权限/项目上下文、请求字段与值、跨页选择、禁用、错误、焦点、地图与工作流保留均有实际用例。`20260921T084726416643Z-ui-navigation-final`另验证10项页面分发边界。

截图路径：`artifacts/navigation/{before,after}`、`artifacts/ui-consistency/{before,after,coverage}`。旧导航为平铺式，旧版无折叠态；新版展开/折叠另存。失败记录保留在evidence，最终通过不覆盖失败历史。

主后端按要求未重启；页面分发修复已在隔离环境验证，在线实例加载列入后续维护部署。UI/NAV通过不代表全范围科研软件验收完成。
