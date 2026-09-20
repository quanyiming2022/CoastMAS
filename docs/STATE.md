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
- 工作流图显示真实数据/模型/输出和节点、连接错误；选择场景预检后运行，服务端再次检查。可编辑 Studio 已接入草稿预检、拖拽端口、输入输出、参数和版本保存，真实浏览器拖入/连线/删除/参数/绑定/输出/复制/修订/历史/运行通过。
- 运行页真实轮询/取消/重试/快照；结果页真实下载、来源、离线多边形地图、分区人口图表和统计表；全部基于实际输出。地图使用 MapLibre 6 的 Vite `?worker&url` 打包，不依赖外部底图。
- 浏览器真实链路已通过：登录→预检→Redis→独立 worker→S3/PG 发布→结果/下载；面积 80000 m²、估算人口 320、3 节点、执行阶段 LLM=0。桌面/手机截图在 `artifacts/screenshots/`。
- 地图缺失 worker、统计未知面积字段误读、登录状态刷新与测试控件定位的失败记录均保留，修正后重跑；不能删除失败制造全绿历史。
- 前端仍缺：完整地图场景编辑、模型注册及完整目录操作、动态评价/协同/研究/管理页面、场景比较/时间序列与全部操作 E2E。当前页面不等于完整 UI 验收。

## 最新证据
- 存储恢复后完整后端：`20260920T140404835174Z-native-storage-backend-full`，267 passed、2 warnings；真实浏览器 `20260920T140404398495Z-native-storage-browser-full`，5 passed。
- 覆盖率 5297/6015 行、1431/2020 分支，最终分支门槛仍未通过，没有排除困难业务文件。
- 工作流草稿预检增量：`20260920T141027639331Z-workflow-draft-preflight` 通过；前端18项测试 `20260920T142517556100Z-workflow-editor-unit` 通过；生产构建 `20260920T142324251056Z-workflow-editor-build` 通过。编辑器两条真实浏览器通过；全套浏览器 20260920T143512052605Z-workflow-studio-browser-full 为 7 passed，最新18项单元与 lint 通过。完整后端 20260920T143514654592Z-workflow-studio-backend-full：269 passed、2 warnings；工作流增量已提交 f9911a2。
- 生成契约源于 Pydantic，漂移检查需纳入统一 Makefile。Vite 图表/地图包体警告、依赖弃用警告保持可见。

## 环境与继续执行
- 本地 API/UI `http://127.0.0.1:58000`，worker 与 beat 已启动；PostGIS 55432、Redis 56379、MinIO 59000。`/health/live` 是进程存活，`/health/ready` 真实检查 DB/S3/Redis；旧 `/health` 只检查 DB。
- Docker 磁盘用户已调整。旧 MinIO 两次 panic 后已切换经校验的官方安全源码原生 ARM 构建，镜像/源码/二进制固定摘要，新卷 coastmas_objects_native。旧卷和私有备份保留；归因未确定。详见 object-storage-recovery.md。
- 外部 LLM 密钥仍缺失，真实外部研究实验 BLOCKED；本地协议测试不能算真实外部实验。独立开发不因此等待。
- 最小下一步：保存工作流编辑增量全套证据，再推进场景工作台及实体绑定。当前 API 日志 api-workflow-editor.log；worker/beat 持续运行。
- 其他必选缺口：时间/跨 CRS 保守分配显式节点、服务/DB 数据连接器、非内置运行审批、完整任务诊断日志、计算结果缓存、孤立存储对象保留清理、可选 GeoAI API、全部研究与性能实验、统一 Docker 部署/Makefile/完整文档和最终门禁。
- 后端回归命令：`.venv/bin/python scripts/evidence.py combined -- .venv/bin/python -m pytest -q --cov=coastmas --cov-branch --cov-report=json:artifacts/coverage.json`。前端：`npm --prefix apps/web test`、`run lint`、`run build`、`run e2e`。
- 平台中断不代表完成，不宣称后台继续执行。只有所有必选项在最终交付代码上有证据通过才宣布完成。

## 后续已完成增量
- 智能规划 UI：数据歧义必须选择，输入变化使旧候选不可保存；外部账本 0/2、换账号缓存清理均有真实/组件证据。规范 JSON 工作流 ID 修复保留旧版本。
- 地理实体：八类实体、严格几何/CRS/时间/身份，PostGIS 不可变派生空间版本，分页空间/时间/历史查询；导入/修订/历史/地图真实浏览器通过。实体历史选择竞态有红绿测试；详见 geographic-entities.md。
- 知识图谱：PostgreSQL 契约投影＋NetworkX，九类关系、版本来源、权限/预算、交互邻域和筛选；契约候选不代表科学通过。真实浏览器通过，详见 knowledge-graph.md。
- 原生 MinIO：11 资产版本/7 旧结果逐字节校验，120 秒并发 200 写/3168 读，重复源码构建二进制摘要一致；恢复后全套回归通过。过去存储崩溃和对应测试失败证据全部保留，不声称长时稳定性已充分验证。
- 真实外部 LLM 配置问题已异步询问一次，无答复；不要重复询问或打印密钥。本地协议回归不能替代真实外部实验。

- 场景工作台增量：entity_references/data_references 精确版本、场景依赖外键、目录范围/时间/实体有效期检查、AOI 绘制上传、参数表单、保存复制历史和实际运行。相关后端72项、浏览器4条通过；AOI视野与实际DEM测量范围复验通过（151408833135Z-scene-measured-extent-browser）；场景显式数据选择与真实输入一致性测试通过（151708565307Z-scene-input-selection-green）。下一项为结果对象和地理实体绑定。详情 scene-workspace.md。
- 当前 API/worker/beat 已统一重启加载场景执行校验，日志 artifacts/logs/{api,worker,beat}-scene-final.log，三者已加载场景数据选择执行约束。所选实体快照进入产物，但完整结果对象到实体/管理结果绑定仍未完成。
- 用户询问进度：已告知按证据关联条目 330/1202≈27%，正式PASS 12/1202≈1%，不把已映射路径等同完成功能。要求进一步节省token，后续只做局部定位/成组修复/相关回归，保留最终完整门禁。

- 结果绑定增量：新增 ResultObject/ResultView，精确匹配场景实体 management_unit_id，重复映射拒绝，缺失保持 UNBOUND/PARTIAL，通用输出 NOT_APPLICABLE；保留原始输出。实际发布 ResultManifest 与数据库 ID/字节 SHA 一致，异质单位 per-output、未知结果范围 null。前端显示固定版本与未绑定项，历史结果兼容。真实浏览器 153804904313Z-result-binding-browser 首次通过，实际 U1 绑定且原金标准不变；截图已目视检查。海岸/评价/时间变化映射和实体到期边界相关34项回归通过（154042079354Z-result-binding-backend-regression）；类型/格式/契约/前端测试与构建通过（154157535990Z-result-binding-final-checks）。详见 result-entity-binding.md。
- 本轮服务日志改为 artifacts/logs/{api,worker,beat}-result-binding-final.log，三者已重启加载结果绑定、发布清单及时间变化/实体到期边界修复。API session96367、worker61173、beat51349；后续更新前确认无活动任务、核对进程和目录。
- 最终当前服务浏览器复验通过：20260920T154406863514Z-result-binding-final-browser；未修改原始样例或覆盖历史结果。下一步继续结果空间联动/多期比较及剩余全范围界面，不重新规划。
