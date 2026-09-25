# CoastMAS 全站现状审计

审计日期：2026-09-23。范围：现状、证据、改进设计和下一轮任务；**本轮不实施业务改造**。

## 结论与当前短状态

全站现状已按入口、代码、接口、任务、模型、权限、说明书和测试建立交叉索引。系统已有真实资产接入和实际计算链路，不能继续沿用“只能读检查报告、模型都不能运行”的旧判断；但最少填写、统一标准适配及正式业务科学依据尚不完备。**不宣布产品全范围验收通过，也不把部分路径实测当成全部条件组合通过。**

- 四份交付：本报告、[inventory.json](inventory.json)、[redesign.md](redesign.md)、[implementation-backlog.md](implementation-backlog.md)。后两份全部是提案，未实施。
- 指定 `docs/coastmas-full-audit-minimal-input-standards-task.md` 未找到。已检索本机相关目录与附件；附件是历史说明及当前指令，未包含独立任务书正文。本轮以用户当前完整指令的只读边界执行；不能核对缺失文件中的额外条款，记 **BLOCKED（范围文件核对）**，不假称已读。
- 先保存现场、后隔离复现。原任务历史研发缺口保留；本轮结束后停止，不自动进入 backlog。

## 设计V2勘误（2026-09-24，非新一轮产品验收）

收到附件后定向核对字段源码，确认此前关键词建议存在语义误判：比较选择不是自动命名，随机种子不是源观测声明，方法依据不等于文件空间范围。共修订10个相关控件建议（UIF-011/023/037/069/116/121/154/155/167/173）；其余建议保留为待实施时语义复核的审阅依据，不能批量自动删控件。

设计同时明确三层复用（文件事实/认可模板/任务绑定）、必选服务端持久草稿、五类任务发起上下文、分离科学状态的一键预检运行，以及无循环的最小契约实施依赖。原四份交付与旧证据索引已保留在artifacts/audits/20260923-full-site/revisions/20260924-design-v2/。

此次仅修订文档/清单并校验一致性；下文运行数据和测试仍是2026-09-23审计证据，**未重跑产品测试、不增加PASS、不实施业务改造**。指定独立审计任务文件仍不能因新附件的设计文字而视作已读取。

## 1. 基线与环境保护

基线与差异见 [baseline-comparison.json](../../../artifacts/audits/20260923-full-site/baseline-comparison.json)，原始 before/after 与既有修改补丁在同目录。

| 检查 | 实际结果 |
|---|---|
| HEAD | `88f7b629c1bde2c91090e2ff1a47917567895b38`，前后相同 |
| 代码/测试/运行包/配置/生产构建 | 427个受保护文件SHA256前后相同；未回退或丢弃既有未提交内容 |
| 正式服务 | API/worker/beat进程身份未变；数据库、对象存储、队列健康 |
| 正式数据 | users/projects/memberships/resources/versions/dependencies/jobs/results/audit等所查表逻辑指纹均未变 |
| 正式任务 | 102成功、1既有失败、无运行/排队；没有把既有失败清掉 |
| 构建 | 隔离构建成功；50个dist文件与当前前端逐文件SHA256一致 |
| 测试隔离 | `/tmp/coastmas-audit-20260923`复制源码；独立随机DB、对象桶、队列与临时容器；测试结束仅清理自己的资源 |
| 本轮新增 | `docs/audits/20260923-full-site/`四份文件；`artifacts/audits/20260923-full-site/`诊断与证据。未改产品、权限、算法、部署配置或正式数据 |

诊断包装器仅替换隔离副本的测试导入，记录操作类别、非敏感值指纹、请求字段路径、响应状态和导航；不记录明文密码。正式环境查询使用只读事务。截图及JSON可能含本机业务资料名，供本地审阅，未上传公开服务。

## 2. 覆盖口径
清单包含 **23个功能组、48个路由声明/条件入口、175个显式控件站点、353个契约叶声明、132个API操作、535个后端函数定义、41个配置读取点、369个Python测试函数定义**。48中包含根重定向和未知路由回退；动态kind循环已展开。175包含共享动态容器，353包含系统与输出字段，不能相加当用户输入量。

浏览器布局覆盖42个具体路由实例×3视口，共126张截图；真实响应轨迹涉及106/132个API操作。未观测接口仍保留源码、请求契约及测试索引，**不计作浏览器实测通过**。响应200只证明收到响应，不等于科学计算有效。

证据等级：EXECUTED=本轮实际执行；SOURCE_CONFIRMED=当前源码确认；DOCUMENT_CLAIM=说明书/历史声明；HYPOTHESIS=需进一步验证。状态PASS/FAIL用于具体验收项；BLOCKED表示缺依据/环境条件；NOT_RUN表示未运行。每个功能的“所有分支运行覆盖”保持NOT_RUN，避免用代表流程替代角色×条件×格式版本的穷举。

### 功能与链路索引

下表只给压缩入口；inventory的每项保留源文件、条件/批量/版本/导入导出清单、接口和关联测试，API操作还保留body schema、响应码及已观察请求字段。

| ID / 功能 | 操作到产物的当前链路 | 条件、批量和历史范围 | 关联测试路径 |
|---|---|---|---|
| AUTH 账号与项目/系统管理 | 身份与项目访问→服务端权限→关系表/审计；不计算科研量 | 登录/退出/项目切换；创建账号/项目、停用启用/系统角色；项目成员增改移除、密码重置撤销会话；项目归档恢复与审计分页 | workspace.spec.ts, navigation.spec.ts, audit-extra.spec.ts |
| NAV 导航与概览 | 角色与当前项目→可见菜单→原路由；偏好仅本机存储 | 独立组折叠及本机偏好；详情归属/前进后退/存储异常；移动抽屉/Esc/焦点返回 | navigation.spec.ts, workspace.spec.ts |
| DATA 数据目录/声明上传/历史 | 填写元数据并选文件→上传/校验→实际存储→预览/历史下载 | 格式分支及变量数组/动态对象；新建、文件校验、保存新版本、旧版本只读；结构预览/质量/原字节下载、分页筛选 | data-workspace.spec.ts, business-import.spec.ts |
| INTAKE 真实影像自动接入 | 上传或授权目录→只读快照/SHA/实际读取→资产登记；不自动生成科学结论 | 浏览器文件/白名单本地来源；来源选择/目录分页/年份可空；2GiB边界/越权路径/重复源文件 | business-import.spec.ts |
| REPORT 业务资料检查报告 | 本地JSON→显示检查事实/声明；无服务端资产写入 | 本地报告文件/全目录筛选/分页/原始详情；模型声明与文件事实/用户声明分栏 | business-intake.spec.ts |
| SOURCE 受控外部数据源 | 选择已批准连接器并填输出声明→真实HTTP/PostgreSQL读取→固定快照 | HTTP/PostgreSQL已授权连接器；格式/变量声明/快照/历史版本；来源失效/权限/SQL与网络边界 | data-sources.spec.ts |
| FRAME 栅格准备模型输入 | 选择至多8固定栅格→同网格/单位检查→分块扫描共同有效交集→显式样本或≤10000全量 | 搜索分页/多栅格选择/波段单位；全量或显式样本/上限/随机种子；聚类或响应变量回归/标准化/时期；网格不一致/共同NoData/依赖与源哈希 | projection-workflow.spec.ts |
| ENTITY 地理实体/版本/空间查询 | 单Geometry/Feature或手绘→CRS/几何校验→实体版本；地图另行空间查询 | 单Geometry/Feature文件/手绘；实体类型/CRS/有效期/版本更新；时空查询/旧版本/结果实体依赖 | entities.spec.ts |
| SCENE 场景空间/范围/资产绑定 | AOI/时期/资源引用→覆盖检查→场景版本→预检和运行 | AOI上传/绘制/资产多选；场景历史/覆盖检查/所需输出/时期；地图图层/影像日期/网络底图/运行绑定 | scene-workspace.spec.ts |
| TEMP 时间适配 | 逐行观测/单位/支撑→类型兼容适配→受管输入→实际worker | mean/sum等方法、变量统计类型和支撑；逐行观测增删/缺测策略/目标时间；预览适配/保存受管输入与场景流程；未保存返回/错误恢复 | temporal.spec.ts |
| MODEL 模型目录/登记/版本/导出 | JSON/YAML或表单→契约/权限校验→声明登记；声明不等于运行资格 | JSON/YAML导入导出/端口参数动态字段；版本/复制/启停/删除依赖保护；能力筛选/类型/运行声明 | model-editor.spec.ts |
| RUNTIME 已提供R模型/审批 | 固定PPCI/pprRFA源码镜像→管理员审批→输入适用检查→容器实际执行 | 提供包可用或缺配置；登记/项目admin审批/版本冲突；PPCI聚类参数或pprRFA响应/项数；运行时固定release/proof与科学输入校验 | projection-workflow.spec.ts |
| DECOMP 模型静态拆解 | Python文本/文件或CLI描述→AST/声明分析；不执行上传代码 | Python静态源码/文件或CLI分支；返回拆解/下载、不可执行上传代码 | model-decomposer.spec.ts |
| KG 知识图谱 | 中心/深度/关系筛选→图构造→真实节点与候选边；候选不等于科学许可 | 中心/关系/深度过滤；节点导航/版本与候选适配边 | knowledge-graph.spec.ts |
| PLAN 智能编排 | 目标/场景→确定性检索或已配置LLM候选→歧义选择→科学检查→工作流 | 场景/管理目标/外部调用许可；歧义候选数据选择/预检/保存工作流 | planner.spec.ts |
| FLOW 工作流编辑/版本/预检 | 模型节点/端口/参数/数据绑定→服务端重算预检→持久化版本与执行清单 | 模型节点、边、端口与发布输出；输入绑定/节点参数/版本编辑；场景预检与失败定位/运行 | workflow-editor.spec.ts, execution.spec.ts |
| RUN 运行中心/取消/重试 | 固定manifest→持久队列→worker真实适配器→成功/失败/取消与结果 | 队列/事件/取消/失败重试；幂等与租约超时/worker产物；固定manifest与请求字段核对 | execution.spec.ts, scene-workspace.spec.ts |
| RESULT 成果/地图/对比/下载 | 实际输出解析→按实体/观测定位→分页/比较→原结果下载 | 分页/双选比较/清除选择/直接链接；地图/结果表不同模型分支/产物下载；来源/校验摘要/样本限定/管理实体 | execution.spec.ts, scene-workspace.spec.ts, projection-workflow.spec.ts |
| ASSESS 指标体系/综合评价/记录 | 公式/单位/方向/范围/权重→观测转换→规则编排→归一化/加权/TOPSIS/变化 | 体系历史/公式源列/参考范围/权重条件；DEMO与正式状态/阈值/目标方法；源观测版本选择/转换/场景规划；评价记录/随机种子/管理单元与年份筛选 | indicator-framework.spec.ts, projection-workflow.spec.ts |
| OPT 空间优化 | 逐条候选/成本/风险/约束→可加性及单位检查→实际优化器→约束核验/分配 | 示范载入/真实手填候选单元增删；预算/风险/面积/可选性/计算时限；保存场景流程/实际求解/重试/结果核验 | spatial-optimization.spec.ts |
| COLLAB 协同方案/评议/比较 | 场景/目标/权重/约束→权限/版本校验→方案；比较与清除选择/分页分组 | 目标/约束动态行/结果引用；版本/人工审核/状态/评论；跨页选择、比较清除、分页 | collaboration.spec.ts |
| RESEARCH 科研验证 | 案例/重复/实验A-B-C/提供方许可→后台真实实验→含失败/缺测的统计报告 | 固定场景模型数据/目标；A-B-C与重复次数/提供方许可；后台研究任务/取消重试/部分失败/统计报告 | research.spec.ts |
| OPS 服务健康、队列租约、对象存储、受控配置 | 服务配置→健康检查/持久队列→租约与重试→实际输出；非新增菜单 | 健康/数据库/对象存储/持久队列；定时任务/租约恢复/隔离配置；日志与身份引用；不增加普通菜单 | 后端健康/队列集成测试 |

没有另造菜单：模型中心、知识图谱、模型拆解、数据源、评价记录及数据准备都已存在；系统管理与项目admin权限是两种不同授权。API-only任务与解析器列入OPS/对应功能组，不以“截图没有”判断未实现。

### 当前业务资产与模型事实

- 本轮只读库：真实业务项目41个GeoTIFF资产条目、2个模型；源目录实际40栅格、2个R源码包，327个文件扫描、0读取错误。41不是新增一种数据：其中两资产SHA相同，名称分别为带目录与不带目录的 `PRD_distance_construction land.tif`；见 `business-asset-summary.json`。二者可能有独立版本/声明意图，本轮不擅自合并。
- 41条资产的`ingestion_state`均为`INGESTED_PENDING_MAPPING`；这表示文件已受管，不能据此称正式科学输入已全部准备好。
- 全库61个模型记录，其中35声明EXECUTABLE、26声明NOT_EXECUTABLE；记录不等于独立实现，也不证明每条历史模型都在本轮执行。模型端口/版本/状态见 inventory.registered_models。
- 本轮重新比较PPCI 0.1.5、pprRFA 0.2适配器与原R包：iris技术夹具聚类共组差异0、回归最大绝对误差0。实际PRD四个大文件再次跑过400行显式样本的PPCI与pprRFA工作流、真实worker、结果位置、表格和下载；证据 `model-numerical.json`、`real-model-workflows/{result,regression}.json`。
- 四个真实文件各418826745字节；共同有效交集、行列位置与源哈希均校验。评价输入桥接400行m→km最大误差`3.552713678800501e-15`。工程响应列/参考范围只用于测试；**聚类不是综合评价，训练拟合不是业务预测验证，样本不是全图成果**。
- 本地检查报告仍将源码包标为NOT_EXECUTABLE，因为不读取当前项目审批状态。这是报告职责/状态解释问题，不能反推现有运行包无效。
- 合成演示和待归档旧影像项目仍存在，包含历史浏览器模型/记录。它们不在真实业务项目内；未按旧清理需求删除，留给独立的归档设计，保留历史。

## 3. 操作负担实测

口径：下表是**现有自动化路径的可观察动作**，不是人工平均耗时、最优路径或独立信息量；同一输入的修改、搜索、回看会重复计数。API预置场景/模型/数据未算手填，所以研究/工作流少填不等于用户从零只需这些步骤。代码/JSON一次fill可能包含几十项事实；鼠标拖拽和未包装浏览器上下文未计入。导航含登录/测试准备，不全是可避免往返。

“提交/检查”按按钮文字归类，包含保存、校验、运行；不等于全部必要确认。重复指纹是需审查的候选，不能自动判定冗余。真实科研人员首次使用的认知时间与恢复时间 **NOT_RUN**。

| 流程（测试文件） | fill | 选择 | 勾选 | 文件 | 点击 | 提交/检查候选 | 导航事件 | 重填候选 | 自动秒数 | 单项最近状态 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| knowledge-graph.spec.ts | 0 | 5 | 0 | 0 | 2 | 0 | 5 | 0 | 2.840 | PASS |
| model-editor.spec.ts | 13 | 3 | 0 | 1 | 11 | 5 | 22 | 1 | 7.260 | PASS |
| audit-extra.spec.ts | 16 | 6 | 0 | 0 | 15 | 8 | 10 | 0 | 5.260 | PASS |
| zz-ui-coverage.spec.ts | 0 | 0 | 0 | 0 | 0 | 0 | 86 | 0 | 39.263 | PASS |
| projection-workflow.spec.ts | 13 | 4 | 1 | 0 | 19 | 7 | 24 | 3 | 175.535 | PASS |
| data-sources.spec.ts | 12 | 7 | 0 | 0 | 10 | 6 | 12 | 0 | 7.021 | PASS |
| workflow-editor.spec.ts | 2 | 3 | 1 | 0 | 6 | 2 | 6 | 0 | 2.454 | PASS |
| workflow-editor.spec.ts | 2 | 2 | 0 | 0 | 10 | 4 | 12 | 0 | 10.188 | PASS |
| scene-workspace.spec.ts | 1 | 1 | 3 | 0 | 11 | 1 | 10 | 0 | 8.632 | PASS |
| scene-workspace.spec.ts | 6 | 0 | 2 | 1 | 10 | 2 | 7 | 0 | 3.346 | PASS |
| scene-workspace.spec.ts | 0 | 0 | 2 | 0 | 1 | 0 | 6 | 0 | 15.772 | PASS |
| scene-workspace.spec.ts | 0 | 4 | 0 | 0 | 4 | 2 | 8 | 0 | 9.428 | PASS |
| navigation.spec.ts | 0 | 0 | 0 | 0 | 2 | 0 | 6 | 0 | 3.003 | PASS |
| navigation.spec.ts | 3 | 2 | 0 | 0 | 75 | 10 | 37 | 0 | 8.329 | PASS |
| planner.spec.ts | 1 | 2 | 0 | 0 | 5 | 3 | 5 | 0 | 3.223 | PASS |
| business-import.spec.ts | 4 | 6 | 0 | 1 | 3 | 1 | 10 | 0 | 172.482 | PASS |
| business-intake.spec.ts | 3 | 0 | 0 | 2 | 2 | 0 | 6 | 0 | 2.458 | PASS |
| collaboration.spec.ts | 12 | 2 | 0 | 0 | 17 | 5 | 8 | 0 | 8.535 | PASS |
| execution.spec.ts | 0 | 1 | 0 | 0 | 7 | 2 | 7 | 0 | 7.877 | PASS |
| temporal.spec.ts | 14 | 1 | 0 | 0 | 6 | 3 | 7 | 0 | 9.104 | PASS |
| ui-consistency.spec.ts | 18 | 7 | 24 | 0 | 15 | 3 | 13 | 0 | 7.162 | PASS |
| workspace.spec.ts | 0 | 0 | 0 | 0 | 6 | 0 | 9 | 0 | 2.722 | PASS |
| data-workspace.spec.ts | 12 | 8 | 0 | 1 | 11 | 3 | 13 | 0 | 6.855 | PASS |
| indicator-framework.spec.ts | 10 | 3 | 1 | 0 | 14 | 6 | 20 | 0 | 17.328 | PASS |
| research.spec.ts | 0 | 1 | 4 | 0 | 7 | 2 | 7 | 0 | 4.722 | PASS |
| spatial-optimization.spec.ts | 18 | 2 | 0 | 0 | 16 | 6 | 18 | 7 | 18.707 | PASS |
| model-decomposer.spec.ts | 4 | 3 | 0 | 1 | 5 | 4 | 5 | 0 | 2.255 | PASS |
| entities.spec.ts | 5 | 0 | 0 | 1 | 4 | 3 | 5 | 0 | 2.333 | PASS |

首轮失败轨迹保留在`browser-first-run/`，最终逐项轨迹在`browser/`；同测试文件可能有多个场景，标题与证据文件在inventory中可区分。整套状态仍以T03为准。

恢复成本实测：时间适配表单只填名称→离开到数据目录→浏览器后退，名称由`audit-unsaved-draft`变为空，至少1个已填字段需重填；没有把单字段结果外推为所有页面必丢失。失败请求后保留输入、运行重试/租约恢复有现成单元和集成测试，但全站断网/刷新/版本冲突恢复组合尚未穷举。

## 4. 问题与共同根因

| 问题 | 当前事实/证据等级 | 根因与后续对应 |
|---|---|---|
| P01 / INTAKE、DATA | 普通自动入口只支持TIFF，其他格式先填声明（EXECUTED+SOURCE_CONFIRMED）；DataImport.tsx; DataMetadataForm.tsx; data-workspace.spec.ts | D01 → B02 |
| P02 / DATA、MODEL、SOURCE、FLOW | 通用schema编辑器把类型/结构/内部键暴露为用户输入（EXECUTED+SOURCE_CONFIRMED）；ScientificFields.tsx; frontend-index.json; screenshots/20-1440.png | D02 → B03 |
| P03 / TEMP、SCENE、OPT、COLLAB | 上下游没有统一的有效来源声明和变量映射复用（EXECUTED+SOURCE_CONFIRMED）；TemporalAdaptation.tsx; SpatialOptimization.tsx; browser temporal/spatial-optimization | D03 → B04 |
| P04 / TEMP、DATA | CF容器数值可读，但日历/边界/统计支撑未随计算值传递（EXECUTED）；standard-probes.json CF case; core/data_inspection.py | D04 → B05 |
| P05 / DATA、ENTITY、SOURCE | 多图层、CSV方言、实体集合与标准版本缺少共同适配计划（EXECUTED+SOURCE_CONFIRMED）；standard-probes.json CSV case; data_inspection.py; Entities.tsx | D04 → B05 |
| P06 / TEMP、SCENE | 用户年份声明、技术时间默认值与实际观测支撑需要分开（SOURCE_CONFIRMED）；Entities.tsx valid_from default; RasterFrame.tsx; source-inspection.json | D03 → B04 |
| P07 / OPT | 候选单元/面积/风险/成本等主要依赖逐项填写（EXECUTED+SOURCE_CONFIRMED）；SpatialOptimization.tsx; spatial-optimization.spec.ts | D05 → B07 |
| P08 / ENTITY | 实体入口以单几何/单Feature创建为主，无集合到实体批量映射（EXECUTED+SOURCE_CONFIRMED）；Entities.tsx; geography_routes.py; entities.spec.ts | D05 → B06 |
| P09 / TEMP | 已有资产到时间观测的读取映射未接入普通时间表单（EXECUTED+SOURCE_CONFIRMED）；TemporalAdaptation.tsx; temporal.spec.ts | D05 → B06 |
| P10 / FRAME、RUNTIME | 真实栅格模型输入仅支持明确样本或有限全量，不是全图推理（EXECUTED+SOURCE_CONFIRMED）；core/raster_frame.py; real-model-workflows/result.json | D06 → B08 |
| P11 / TEMP | 离开时间表单再返回，未保存名称丢失（EXECUTED）；role-recovery.json | D07 → B09 |
| P12 / RUNTIME、REPORT | 本地检查报告的模型不可执行状态与当前审批注册状态不相通（EXECUTED+SOURCE_CONFIRMED）；source-inspection.json models; registered-models.json; ProvidedModels.tsx | D08 → B10 |
| P13 / DATA、INTAKE | 同项目同字节文件出现两个资产，复用/另建意图未在入口集中处理（EXECUTED）；business-asset-summary.json duplicate checksum | D01 → B02 |
| P14 / AUTH、COLLAB | 管理成员/重置密码/结果引用仍要求内部标识（EXECUTED+SOURCE_CONFIRMED）；Admin.tsx; Collaboration.tsx; audit-extra.spec.ts | D02 → B03 |
| P15 / MODEL、RUNTIME | 模型技术通过/审批/输入适用/业务验证不是一个统一状态视图（EXECUTED+SOURCE_CONFIRMED）；model-numerical.json; projection_routes.py; real-model-workflows/regression.json | D08 → B10 |
| P16 / NAV、FRAME | 全套浏览器受共享数据数量和历史基线文件影响，整套首轮失败（EXECUTED）；browser-run.log; browser-supplement.log | D09 → B01 |
| P17 / ASSESS、OPT、RUNTIME | 真实指标/分类/A-B-C/目标或响应变量及科学方法认可仍缺依据（EXECUTED+SOURCE_CONFIRMED）；source-inspection.json; real-model-workflows/* scope flags; user declarations | D03 → B04 |
| P18 / RESULT | 工程样本地图/拟合结果已存在，但不是正式分区/全域成果（EXECUTED）；real-model-workflows/result.json; regression.json; ProjectionResultView.tsx | D10 → B11 |
| P19 / DATA、SOURCE | STAC/CSVW没有完整读取-映射-任务-导出链路（SOURCE_CONFIRMED）；source_routes.py; data_inspection.py; standards S07/S09 | D04 → B05 |
| P20 / NAV、AUTH | 旧合成与历史测试资源仍存在；须区分历史保留与默认工作入口（EXECUTED）；project-resource-summary.json; registered-models.json | D11 → B12 |
| P21 / RUN、RESEARCH、FLOW | 运行恢复已有后台机制，但缺跨页任务草稿/来源解释串联（EXECUTED+SOURCE_CONFIRMED）；test_jobs.py; execution.spec.ts; role-recovery.json | D07 → B09 |
| P22 / DATA、MODEL、ASSESS | 资源版本不能替代文件标准/词表/方法/契约版本（SOURCE_CONFIRMED）；contracts.py; contracts.schema.json; inventory standards | D04 → B05 |
| P23 / PLAN、KG | 规则与知识候选不能自动认定语义等价，模糊项仍需绑定决策（EXECUTED+SOURCE_CONFIRMED）；planning_routes.py; knowledge_graph_routes.py; planner.spec.ts | D03 → B04 |
| P24 / AUTH、NAV | 角色主路径已测，全部功能×角色×异常分支未穷举（EXECUTED）；role-recovery.json; backend-tests.xml; python_test_index | D09 → B01 |

共同根因不是按钮颜色或字段不够：①文件接入与声明编辑的契约倒置；②数据事实、用户声明、语义映射、方法适用和审批状态分散；③下游表单直接组装内核JSON，缺共用资产映射层；④资源版本已有，但标准/词表/方法版本与复用失效条件尚未统一；⑤后台任务可恢复，用户的未完成任务上下文不能恢复。设计据此修共用模块，不逐页复制导入器。

## 5. 标准与版本：逐层能力矩阵

每格是当前证据，不是整项符合性认证。存在原文件下载不代表可逆派生成果导出；依赖库能读取某格式，也不代表系统保留其全部语义。

| ID / 标准与版本 | 识别 / 校验 | 语义读取 / 映射 | 任务使用 / 导出 | 信息损失或拒绝边界 |
|---|---|---|---|---|
| S01 GeoTIFF；文件版本未登记；候选OGC 1.1 | TIFF魔数自动；新入口无需先声明；结构/SHA/CRS/波段/NoData；2GiB磁盘入口 | 技术事实与用户声明隔离；类别含义不自动得出；单波段映射/同网格frame；通用绑定支持明确转换 | 真实40文件/PRD样本实际worker已测；全图大模型未完成；原始文件无损下载；派生frame/JSON结果 | 源文件保留；frame仅交集/显式样本 |
| S02 COG；OGC COG 1.0候选；未按版本声明能力 | 自动TIFF入口将资产登记为GeoTIFF；声明入口检查LAYOUT=COG；非完整COG符合性测试 | 沿用GeoTIFF；未验证全部HTTP Range/金字塔要求；同TIFF | 完整下载后本地读取；不能当作远程分块COG服务；原字节下载；未实现COG标准化成果导出 | 原字节不丢；优化传输能力未证明 |
| S03 GeoJSON；RFC 7946部分行为 | 普通声明上传需选格式；实体入口Geometry/Feature；FeatureCollection解析/2D有效性/经纬度；拒legacy crs | 字段保留但科学变量需声明；属性不能自动当指标；矢量资产与实体创建入口割裂 | 已有矢量/实体/空间查询实际测试；原文件+空间查询FeatureCollection | 科学含义/ID映射非自动；3D拒绝 |
| S04 GeoPackage；文件版本未检测；候选1.3/1.4.0配置档 | 需用户声明GeoPackage；只接受单图层；多图层明确拒绝 | CRS/几何/属性；扩展表/样式/关联未承诺；没有图层选择拆分流程 | 单图层解析有测试，完整标准族未实测；原文件下载；无完整包往返生成 | 原文件保留；多图层不可用而非静默取首层 |
| S05 Shapefile ZIP；依赖驱动；未记录规范/编码档案 | 需声明ZIP和格式；配套文件/路径安全/单图层/几何 | 需人工单位/字段意义；编码依赖驱动；缺字段别名模板 | 现有解析测试；原ZIP下载 | 字段截断/编码损失未建立专项往返矩阵 |
| S06 CSV；UTF8/BOM逗号子集；不是任意CSV方言 | 需预声明CSV/变量；表头唯一/行长/数值/100000行限制 | 单位从声明；无类型/时区/语义元数据自动继承；无CSV字段到评价/优化/时间的统一映射器 | 逗号零/负值实测；分号样例拒绝；原文件/来源快照CSV | 字符原值保留；计算需要另作科学声明 |
| S07 CSVW；W3C Recommendation 2015候选 | 未实现；未实现配套metadata识别 | 未读取column datatype/null/unit扩展映射；待设计绑定器 | NOT_RUN/当前无连接链路；未实现CSVW导出 | 不能把普通CSV上传算CSVW支持 |
| S08 NetCDF/CF；容器可读；未按CF版本验证；官网当前1.13 | 需声明NetCDF/变量；仅声明变量数值/units/形状/预算 | 实测CF-1.12 360_day/bounds/cell_methods未进入任务值；缺CF轴/日历/标准名版本适配 | 数值可读不代表CF时间科学适用；原文件保留；未输出CF成果 | 派生数值丢失时间轴语义；非Gregorian不得转UTC猜填 |
| S09 STAC；拟按STAC版本/扩展登记；当前不支持 | 未实现Item/Collection自动判别；未实现STAC schema/profile校验 | 无assets/时间/投影扩展解析；不能以已有HTTP连接器替代 | 外部HTTP快照实测，STAC任务NOT_RUN；未实现STAC导出 | 不能承诺资产关系/扩展保留 |
| S10 OGC API Processes；Part1 Core 1.0作为评估候选 | 无标准发现/符合性路径；CoastMAS自有FastAPI契约 | 自有模型端口并非标准process description；需独立适配壳和能力声明 | 内部Job/worker实测；标准服务NOT_RUN；自有JSON输出；非标准符合性 | 输入/输出格式、异步状态需显式映射 |
| S11 CRS/单位/语义；PROJ/Pint实现版本可固定；语义映射未注册词表版本 | TIFF/矢量读CRS；单位存在时读取；严格CRS、单位量纲、变量统计支撑 | exact_standard_name或approved_mapping，不用相似度放行；单位转换/重投影/重采样有内核；复用审批缺范围化字典 | 相关后端测试；跨CRS总量守恒完整产品路径有缺口；来源/变换清单；无标准元数据侧车统一导出 | 垂向/总量/类别转换不能静默改变 |
| S12 科学评价/优化方法；自定义ModelSpec/IndicatorFramework版本；无已认证行业标准档案 | 普通方法选择；不自动识别行业依据；固定minmax/权重/公式/单位/可加性/预算科学校验 | 没有自动国家/行业标准匹配依据；可复用已存体系，仍需大量手建定义 | 综合/TOPSIS/变化/优化实际测试；PPCI聚类与回归不可冒充评价；JSON结果+manifest；无行业制式成果导出 | 换权重/阈值/方法不具有结果等价性 |
| S13 模型JSON/YAML；CoastMAS自有schema；版本是资源版本并非schema迁移版本 | 根据导入入口解析JSON/YAML；契约/许可/重复键/不可执行声明 | 端口、单位、约束需维护者定义；非任意上传代码运行；固定release审批 | 内置与两提供模型实际测；任意第三方适配NOT_RUN；JSON/YAML/版本历史导出 | 旧schema兼容策略未做显式版本协商 |
| S15 CoastMAS领域JSON资产；自有契约 | 声明JSON；重复键/非有限数/结构预算与声明变量校验 | 领域frame由各内核再验；无通用业务映射 | 真实时间/评价/优化/投影派生输入已测；原JSON与结果下载 | 任意额外属性不保证进入计算；领域schema版本需明确 |

本轮针对性实测：UTF8 BOM逗号CSV可读0/负值；分号CSV被当单列而缺声明字段；CF-1.12、360_day、time bounds/cell_methods未带入计算值；实际COG字节可被TIFF通道读取，但未作完整COG标准验证。详见 `standard-probes.json`；其中execution=PASS表示诊断成功记录现象，observed_error仍是产品拒绝，不是对应格式支持PASS。

版本依据仅用于下一轮配置档候选，不宣称已实现：[GeoTIFF](https://www.ogc.org/standards/geotiff/)、[COG 1.0](https://docs.ogc.org/is/21-026/21-026.html)、[GeoPackage 1.4.0](https://www.geopackage.org/spec140/index.html)、[GeoJSON RFC7946](https://www.rfc-editor.org/info/rfc7946/)、[CSVW](https://www.w3.org/TR/tabular-metadata/)、[CF官网](https://cfconventions.org/)、[STAC](https://stacspec.org/en/about/stac-spec/)、[OGC API Processes Core 1.0](https://docs.ogc.org/is/18-062r2/18-062r2.html)。CF官网本轮显示1.13；测试夹具1.12并非“最新版本”。Shapefile/编码档案和各第三方扩展的完整规范级符合性均未认证。

## 6. 验证结果与限制

| 项目 | 结果 | 证据/说明 |
|---|---|---|
| 后端现有测试 | PASS：487项、33条warnings | backend-tests.xml / .log；警告未屏蔽 |
| 前端组件/交互 | PASS：33文件65项 | frontend-tests.log |
| 前端lint/类型/隔离构建 | PASS | 对应日志；首次从错误目录构建失败保留，纠正工作目录后通过 |
| 首轮完整浏览器套件 | **FAIL：25/27，2失败** | browser-run.log；不能把分开重跑说成整套通过 |
| 原失败1：真实模型流程 | 在单独隔离上下文PASS | 大目录前20条没有目标资产，测试未搜索；属于测试数据依赖/入口发现负担，未改产品 |
| 原失败2：UI提交语义 | 补齐隔离副本原有历史基线后PASS | 首轮ENOENT；没有更新基线消灭差异，历史请求字段/值比较实际通过 |
| 新增角色/恢复诊断 | 最终PASS（成功记录恢复缺陷） | 两次诊断定位错误保留；最后role-recovery.json。PASS不代表草稿已修好 |
| 系统管理与项目角色 | 5种项目角色系统管理均403；VIEWER/PUBLIC创建场景403，MANAGER/RESEARCHER/ADMIN 201 | 无效本地来源各角色403原因不同，不据此推断所有可写角色不可导入 |
| 管理员写操作 | 隔离UI创建账号/角色变更/重置密码/停用再启用实际完成 | 未操作生产账号；所有角色×所有端点完整组合NOT_RUN |
| 模型原实现对照 | 两模型PASS，回归误差0 | model-numerical.json；固定iris技术夹具 |
| 真实业务工程闭环 | PPCI、pprRFA样本流程和评价转换PASS | real-model-workflows/，不等于正式业务验收 |
| 布局 | 42路由×1440×900、1366×768、390×844自动检查无整页溢出/检测到的按钮重叠 | screenshots/coverage.json；不是全部可访问性审计 |
| 截图人工查看 | 已查看声明上传、时间适配、手机优化、系统管理、真实模型结果 | screenshots/及real-model-workflows/；没有做新旧改造对比，因为本轮未改UI |
| 真正外部提供方/互联网所有标准服务 | NOT_RUN | 当前测试配置/固定响应不等于外部服务承诺；不新增费用或公开发送业务资料 |
| 科学结论 | BLOCKED | 指标类别/方向、A-B-C、认可方法、正式预测目标与验证样本、TN正确CRS和来源许可依据不足 |
| 完整人因研究/每种动态组合 | NOT_RUN | 自动化计数仅给可复现起点，不能伪造用户耗时 |

截图按coverage.json顺序命名`00..41-宽度.png`；例如20=声明上传、04=时间适配、24=新建优化、15=系统管理。126张是本轮真实截图，未更新任何产品视觉快照。

## 7. 最少待补科学信息（不作为停止工程的理由）

1. 指标字典：各缩写、原值/重分类、分类编码、正负方向及A/B/C含义；可一次提供表，不按文件反复问。
2. 正式优先任务和认可方法：评价的归一化/权重/参考范围，优化的目标/成本/保护约束，或回归真实响应与独立验证设计。已有工程夹具不能代替。
3. TN正确投影或可信对应文件；“与其他文件相同”不能覆盖当前坐标数值冲突。2022年、非商业、距离m保留为用户声明；具体来源URL与许可条款未核实。

已有真实文件/模型、历史版本、旧入口和科研约束均保留。上述缺口只限制对应正式计算；下一轮解析、映射、草稿、版本档案和界面复用工作无需等待这些科学答案全部齐全。

## 8. 证据重现与交付边界

诊断源码在 `artifacts/audits/20260923-full-site/diagnostics/`；索引脚本、角色诊断、前端记录器、标准探针均保留。重跑浏览器应从原`prepare-isolation.py`准备新的临时路径并复制已有基线，不使用生产项目作测试夹具，不直接复用已清理的隔离DB。测试结果以本轮日志为准，重跑应使用新输出目录避免覆盖。

本轮交付是审计发现与设计，不含修复。完整浏览器套件失败、未穷举分支、缺失范围文件和科学阻塞均保留；不能据此报告“全部必选项PASS”或给出虚构研发完成百分比。
