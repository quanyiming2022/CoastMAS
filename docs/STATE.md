# CoastMAS 当前状态（未完成全范围验收）

## 约束与工作入口
- 项目已移动至 `/Users/quanyiming/projects/CoastMAS`（系统真实大小写 Projects）；原 Documents 目录已验证移走。用户一次委托、连续执行，不等待例行确认。主执行者单独推进，没有子代理。
- 全部任务书和 EQ 已读。后续用 `requirements-index.md` 定位，不重新全仓规划。唯一需求映射为 `requirements-traceability.csv`；映射的 NOT_RUN 不因组件通过而批量改为 PASS。
- 最近提交用 `git log -1` 查看；本状态只记录当前事实。所有命令显式工作目录；源码、测试、迁移、部署或样例文件在 evidence.py 运行期间不得修改。
- 密钥 `.env` 与演示账号 `artifacts/runtime/demo-access.json` 权限 0600，忽略提交，不打印。原始私有运行日志和浏览器 trace 在 artifacts/logs、artifacts/runtime；公开 evidence 自动脱敏，保留失败历史。

## 已实现基础
- 严格不可变版本契约、DAG 科学预检、精确语义/Pint 单位/PyProj CRS/垂向/时间/尺度/NoData/总量守恒；未知科学规则拒绝。可信运行注册固定完整 ModelSpec 摘要，元数据导入不能自证可执行。
- 综合评价、熵权、TOPSIS、多期比较、连通淹没筛查；AST 栅格计算/分区/适宜性、MILP、固定种子分组随机森林与签名私有模型。六类实际 Adapter（Python/CLI、Docker、HTTP、RasterGIS、ML），有进程超时/取消/资源边界。
- PostgreSQL 用户/项目/四角色/不可变资源/引用/审计/任务/结果/规划账本；迁移至 0006。Argon2+不透明会话+CSRF，服务端权限与并发版本保护。Redis/Celery 持久派发、租约心跳、撤权取消、幂等及原子发布。
- 真实 S3 文件校验与 SHA；GeoTIFF/COG、GeoJSON/Shapefile/GPKG、CSV/JSON/NetCDF 读写和有界检查。NetCDF IO 单线程，检查在独立进程；矢量用 spatial_support，不能假装像元分辨率。
- 8 个内置可信模型：地形 screening/overlay/statistics，评价 normalize/weight/composite/topsis/change。3 个确定性规划 DAG 使用真实样例文件计算。人口在完整单元内均匀分布，AOI 裁剪不重新归一化，未知地形单独计量；不称水动力模拟。
- 规划 API：模板解析、缺失条件、精确版本绑定、保存工作流；外部提供方严格 JSON Schema、无自动重试/重定向、请求/响应上限；每条规划共享默认 2 次原子预算，缓存复用重查权限及资源状态。提供方报告 tokens 才记录，缺失保持 null。
- 项目/真实 Dashboard/账号/成员/审计 API；模型拆解导入导出/复制历史/检索匹配/启停归档；工作流预检/提交、任务取消/重试、结果下载/追溯。模型纯启停可保留已有可信资格，修改科学元数据仍需重新审批。
- 持久初始化：8 模型、11 资产、3 场景、3 工作流；重复初始化不重置用户密码、旧版本或停用状态。`python -m coastmas {init,api,worker,beat}`。

## 当前前端与实测链路
- React/TypeScript strict、TanStack Query、生成契约+AJV/Zod；无任意 any，写请求无自动重试，CSRF/幂等/错误追踪。已接通登录、项目切换、概览、模型/数据/场景/工作流目录与详情、运行/结果中心。
- 工作流图显示真实数据/模型/输出和节点、连接错误；选择场景预检后运行，服务端再次检查。图目前只读；完整可编辑 Studio 未完成。
- 运行页真实轮询/取消/重试/快照；结果页真实下载、来源、离线多边形地图、分区人口图表和统计表；全部基于实际输出。地图使用 MapLibre 6 的 Vite `?worker&url` 打包，不依赖外部底图。
- 浏览器真实链路已通过：登录→预检→Redis→独立 worker→S3/PG 发布→结果/下载；面积 80000 m²、估算人口 320、3 节点、执行阶段 LLM=0。桌面/手机截图在 `artifacts/screenshots/`。
- 地图缺失 worker、统计未知面积字段误读、登录状态刷新与测试控件定位的失败记录均保留，修正后重跑；不能删除失败制造全绿历史。
- 前端仍缺：图谱/实体/地图场景编辑、模型注册及完整目录操作、可编辑工作流、动态评价/协同/研究/管理页面、场景比较/时间序列与全部操作 E2E。当前页面不等于完整 UI 验收。

## 最新证据
- 后端完整：`20260920T114407025040Z-workspace-readiness-full`，229 passed、2 条依赖弃用警告。严格类型 `20260920T114404466768Z-workspace-readiness-types`；ruff check 通过。
- 覆盖率当前 4992/5697 行、1319/1898 分支（约 87.62% / 69.49%）；业务分支及核心覆盖率门槛未通过。没有排除困难业务文件。
- 前端组件/契约：`20260920T121841821255Z-web-coastal-stats-fields`，10 passed。严格类型随 production build 通过；lint 最近 `20260920T121353467038Z-web-result-refined-check`，随后少量地图/字段修改需再检查。
- 生产构建：`20260920T121844962451Z-web-coastal-stats-build` 通过，保留图表/地图大于 500 KB 包体警告，已按需加载，未提高阈值隐藏警告。
- 真实浏览器：`20260920T121848342743Z-web-coastal-map-chart-e2e`，2 passed，包含地图库加载、图表、下载金标准、深链接和退出后 401。只有已覆盖行为通过。
- `scripts/export_contracts.py --check` 当前通过；生成 TypeScript 漂移检查需纳入统一 Makefile。前端 optional fsevents 安装脚本未运行，实际构建与浏览器正常。

## 环境与继续执行
- 本地 API/UI `http://127.0.0.1:58000`，worker 与 beat 已启动；PostGIS 55432、Redis 56379、MinIO 59000。`/health/live` 是进程存活，`/health/ready` 真实检查 DB/S3/Redis；旧 `/health` 只检查 DB。
- Docker 磁盘用户已调整。MinIO hotfix AMD64 镜像曾 Go SIGSEGV（非 OOM）；仅本项目对象卷已私有备份，原镜像重启后完整回归和浏览器计算通过。仿真是否根因未确定，没有降级为较旧 ARM 镜像；详情 environment-blockers.md。
- 外部 LLM 密钥仍缺失，真实外部研究实验 BLOCKED；本地协议测试不能算真实外部实验。独立开发不因此等待。
- 最小下一步：保存本轮 UI 检查与文档；完成实体/图谱/协同/评价/研究等必选范围。维护已实现科学组件，不重新生成项目。
- 其他必选缺口：时间/跨 CRS 保守分配显式节点、服务/DB 数据连接器、非内置运行审批、完整任务诊断日志、计算结果缓存、孤立存储对象保留清理、可选 GeoAI API、全部研究与性能实验、统一 Docker 部署/Makefile/完整文档和最终门禁。
- 后端回归命令：`.venv/bin/python scripts/evidence.py combined -- .venv/bin/python -m pytest -q --cov=coastmas --cov-branch --cov-report=json:artifacts/coverage.json`。前端：`npm --prefix apps/web test`、`run lint`、`run build`、`run e2e`。
- 平台中断不代表完成，不宣称后台继续执行。只有所有必选项在最终交付代码上有证据通过才宣布完成。

- 最新增量：智能规划页面已接通；数据歧义必须选择，输入变化后旧规划不可保存，外部账本 0/2 经真实浏览器验证。共享 ProviderPlanningArtifact 保留未知 usage 与需复核标记；本地提供方协议回归17项通过。
- 发现并修复同一场景仅JSON对象键顺序不同就产生不同工作流ID的问题；旧资源保持原标识，新规划使用规范JSON摘要。相关科学/样例13项回归通过。目录展示标识片段，测试按选定唯一身份与清单核对，不假设名称唯一。
- 会话过期和换账号清除私有查询缓存已有红绿回归。前端目前11项测试通过，最新真实浏览器 `20260920T124618439609Z-web-canonical-e2e` 3 passed。完整后端增量回归 `20260920T124636108740Z-planner-web-core-full`：231 passed、2 warnings。类型/lint 通过；入口文件仅修正格式后重新格式检查通过。
- 已异步请求用户在项目 .env 配置外部 LLM 端点、模型与密钥，未在对话收集密钥。等待配置不阻止独立开发；未提供时继续标记真实外部实验 BLOCKED。

- 新增 GeographicEntity：八类实体、严格几何/CRS/时间/身份校验；PostGIS 不可变派生空间版本与资源同事务写入，分页空间/时间/历史查询。页面支持导入、修订、历史读取与点线面地图；真实浏览器证据 20260920T130926122354Z-geography-browser 通过。详见 geographic-entities.md；完整场景工作台仍未完成。API 当前日志 api-geography.log。

- 实体增量统一回归：20260920T131213156037Z-geography-backend-full，262 passed、2 warnings；20260920T131222098930Z-geography-ui-all-browser，4 passed。Python lint/format、类型、契约漂移、生产构建均通过。当前覆盖行 5128/5837，分支 1363/1944；最终覆盖门槛仍未通过。下一项：知识图谱及完整场景关系。

- 知识图谱增量：PostgreSQL 契约版本投影＋NetworkX 3.6.1（BSD-3-Clause），九类关系、来源版本、权限/预算限制、交互邻域/关系筛选/证据分页已实现。契约候选不等于科学预检通过，运行配置与存储 URI 不进入图响应。真实浏览器 20260920T132950224396Z-knowledge-graph-focus-browser 通过；完整回归进行中。当前 API 日志 api-knowledge-graph.log。
- 最新完整回归未通过：20260920T133027591712Z-knowledge-graph-backend-full（238 passed / 29 errors）及 20260920T133035539580Z-knowledge-graph-all-browser（2 passed / 3 failed）。MinIO 第二次 panic 已停止服务、私有只读备份；原生 ARM 官方安全版源码编译进行中，尚未切换对象卷。实体历史选择竞态已用受控延迟红绿测试修复，14项组件及实体/图谱两条浏览器复测通过。当前对象存储故障不能计为验收通过。详情 environment-blockers.md。
