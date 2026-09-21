# CoastMAS 当前状态（未完成全范围验收）

## 执行约束
- 项目已移动至 `/Users/quanyiming/projects/CoastMAS`（实际大小写 Projects）；工作目录必须显式指定。用户授权一次委托连续研发，不等待例行阶段确认；默认一个主执行者，未调用子代理。
- 完整需求和 EQ 已读，用 requirements-index.md 定位后续条目；唯一映射 requirements-traceability.csv。组件证据不等于全范围最终 PASS；不重新规划、不重造已验证算法。
- evidence.py 在运行前后计算源码摘要；运行期间不得修改 src/tests/scripts/apps/migrations/deploy/sample-data 或构建配置。文档可更新。完整失败记录保留，不放宽断言或删测试求绿。
- 私有 `.env`、`artifacts/runtime/demo-access.json` 和连接器配置为 0600，忽略提交，不打印。evidence 自动脱敏；提交前核查暂存差异中的 configured_secrets。API/worker 私有日志保存在 artifacts/logs。

## 已实现与对应文档
- 不可变 Model/Scene/Workflow/Binding/Manifest 契约，DAG 科学预检、语义/单位/CRS/垂向/时间/尺度/NoData/总量守恒；未知约束拒绝。固定 ModelSpec 摘要可信运行注册。Python/CLI/Docker/HTTP/GIS/ML 适配器、隔离超时及取消。
- PostgreSQL/PostGIS 四角色与 PUBLIC 受限读、Argon2 会话/CSRF、版本/依赖/审计/任务/规划账本；Redis/Celery 派发、租约、幂等、撤权和 S3 原子发布。迁移0006，旧版本与用户状态保留。
- 真实八种格式文件检查/预览/下载，项目对象隔离、上传修订/质量版本、全目录搜索；data-workspace.md。受控 HTTP/PostgreSQL 数据源配置、登记、历史、幂等导入和来源外键；data-sources.md。
- 模型表单/导入导出/历史/复制/启停/归档/检索，五种静态拆解候选；model-center.md。非内置可信审批闭环仍待完成。
- ReactFlow 工作流编辑、绑定/预检/保存/历史/实际运行；workflow-studio.md。场景 AOI 编辑、真实范围检查、精确实体/数据版本绑定；scene-workspace.md。
- 八类地理实体/PostGIS不可变空间版本；geographic-entities.md。PG→NetworkX 九关系与版本来源；knowledge-graph.md。确定性三模板规划、数据歧义显式选择、外部结构化候选及原子2次预算，不能绕过科学预检。
- 结果对象固定实体版本、实际发布 Manifest 与 SHA、历史几何地图/图表/数值时间轴/双运行原值比较；result-entity-binding.md、result-center.md。
- 科学算法：地形连通 screening（不是水动力学）、真实叠置/人口/未知面积，固定边界评价、等权/手工/熵权、单期TOPSIS、多期变化/趋势；安全AST/有单位数组表达式、MILP、分组隔离ML。原样例金标准：A=80000 m²/320人口、baseline=40000/160；B=.2/.4/.6/.8；C变化.2、趋势.1/年。

## 本轮评价中心增量（已验证）
- IndicatorFrameworkSpec/IndicatorDefinition：全字段、明确单位/固定边界、多列公式、方向/共享权重、五种 DEMO 分类；无科学边界的草稿不可保存。体系不可变CRUD/历史/归档、真实S3准备文件、双来源FK、幂等、固定权重的评价方案→保存工作流→独立worker运行。
- `/assessments` 编辑/历史/公式输入/准备/方案界面；DataWorkspace 增加经核实的体系/观测来源及历史深链接。未运行的自动权重不伪造。
- 四种空间支撑各有独立可信签名：management_unit、administrative_unit、custom_polygon、grid。旧5个评价签名和3个海岸签名原样保留，新增15个签名。主库已幂等初始化为23模型/11原始样例资产/3原始场景及工作流，保留用户新增数据。
- 多种空间支撑同时存在时，规划仍提供 normalize.frame 数据选择入口；不擅自选择模型。
- 详见 assessment-center.md。新增文件和修改均为本轮工作，评价中心基础增量已提交652bba9；随后评价记录增量也已验证，具体提交标识见 git log -1。

## 最新已通过证据
- 上一完整回归：20260921T015906646890Z-source-catalog-backend-full，304项；20260921T015904965192Z-source-catalog-browser-full，15条。同源SHA 9ba89332db08e47313a0bfe0c3ac08d04006f2f92f2e80b7dc06e6e91129b97b。
- 评价领域/原栅格回归39项（021340547923Z）；版本/真实文件/来源/科学约束16项（024157396725Z-framework-lineage-green）；空间单元/旧样例/规划15项（023851387059Z-assessment-spatial-green）；混合空间支撑选择13项（024605717476Z）。
- 真实单条浏览器：023327232017Z-indicator-framework-browser-run，编辑→文件→方案→独立worker成功→修订与只读历史。后续加强了真实分数/变化/趋势及来源链接断言，正随全套运行。
- 最新静态质量：20260921T024726578244Z-assessment-delivery-quality，全仓ruff、81源文件mypy、生成契约漂移、前端42项测试、lint/生产构建通过。保留包体与依赖警告。
- 本轮完整后端：20260921T024724912482Z-assessment-backend-full，325 passed、2 warnings。首次全浏览器15/16通过，发现新增导航使退出按钮超出视窗；侧栏改为可滚动，保留失败证据。20260921T025316538695Z-assessment-navigation-browser-full 全16条通过，包括评价分数/变化/趋势和历史来源链接。CSS修复后仅重测受影响前端，Python未变化，后端证据继续适用；不声称两个源码整体SHA完全相同。记录增量相关后端12项（20260921T030857627325Z）、前端42项/类型/lint/构建/契约漂移（030948580968Z）和真实浏览器3条（031145675603Z）全部通过。当前没有验收进程运行。
- 最新覆盖率6225/7014行≈88.8%、1656/2292分支≈72.3%；最终分支门槛未满足，未排除困难业务文件。

## 服务与恢复
- API/UI http://127.0.0.1:58000。当前API session88450/log api-optimization.log；worker38305/log worker-optimization.log；beat28693/log beat-data-isolation.log。合成HTTP源20358/log source-acceptance.log，脚本 serve_acceptance_source.py，localhost58090。
- 基础容器 coastmas-database-1(55432)、coastmas-redis-1(56379)、coastmas-object-storage-1(59000/59001)。当前三依赖ready。中断后先检查容器/进程及 `/health/ready`，不要盲目重跑。仅恢复本项目容器，不能删除卷或处理无关项目。
- 原生MinIO新卷coastmas_objects_native，经固定官方源码构建、SHA恢复及120秒并发验证；旧卷和私有备份保留。历史AMD64 panic未抹去，详见object-storage-recovery.md。
- `.env`中的COASTMAS_DATA_SOURCES_CONFIG指向 artifacts/runtime/source-connectors.json（0600），demo-csv仅授权演示项目本机SYNTHETIC源。
- 更新服务前核对jobs无QUEUED/RUNNING，验证精确命令+cwd，正常SIGTERM退出再启动。用户任务中断不代表项目完成，不宣称后台仍在继续。

## 后续必选缺口
- 评价记录已实现：AssessmentSpec固定体系/数据/场景/工作流并建立FK，规划行锁内原子保存工作流与记录；运行复用统一预检和幂等任务，从真实Manifest匹配结果。新增工作流归档及重复请求保护、记录列表/预检/运行/结果分页界面。12项相关后端回归和3条真实浏览器已经通过，包含独立worker数值金标准、结果回看、固定来源导航与工作流回归。API已重启加载，worker计算代码未变。
- 协同模块增量已实现并验证，见下方检查点。下一模块为第31节实际优化及第43节科研运行界面，已定位读取，不重新规划。
- 非内置运行审批、显式时间/跨CRS保守分配节点、完整任务诊断日志、计算缓存、孤立对象保留清理、可选GeoAI API（不得读改GeoAI源码）。
- 外部LLM实验缺凭证，BLOCKED；已异步问过一次，无答复，不重复追问，不把本地协议当外部实验。独立工作继续。
- 全部研究/消融/性能实验、统一Docker应用部署/Makefile（尚无）、准确运行构建身份、完整用户/运维/开发/科研文档和最终覆盖率/全链路/分支审查。只有全部必选项真实证据通过才宣布完成。

## 协同增量检查点
- 新增 core/domain/persistence/app 协同模块、Collaboration.tsx、领域/数据库/API/浏览器测试及 docs/collaboration.md。R30 的18行映射更新，最终状态仍NOT_RUN。
- 方案固定场景版本/权重/硬约束/真实结果引用；版本外键、作者/公众权限、独立人工审核、幂等意见、显式公开与撤回；Pint单位换算后的区间比较不抵消硬约束。VIEWER只读，PUBLIC只参与公开资源及自己的方案。新scene/proposal修订撤回公开。
- 全后端338项：20260921T033942793285Z；全浏览器17条：034148022283Z。静态ruff/mypy86源文件，前端42项/类型/lint/构建和契约漂移通过。
- 随后自查修复VIEWER作者读权限及RunManifest完整SceneSpec引用匹配，定向回归034507133634Z、034736157071Z通过。最终真实浏览器034840135102Z通过：先独立worker海岸结果80000m²/320人，再绑定到方案与历史比较。此前完整回归早于补丁，不声称覆盖同一最终SHA。
- 所有红测试/入口错误/同名测试模块收集失败均保留，没有通过删断言求绿。当前无验收进程，API已加载最终补丁session13356，worker算法未变继续session71412。
- 下一步：复用domain/optimization.py的SciPy MILP/硬保护/可行性验证，接入可信catalog/worker/空间结果/界面。coastal_catalog统一合并模型，sample_bootstrap自动登记全部模型；当前23计数增加新模型时相应更新，已有23签名不可改变。domain/result_views.management_objects需接结构化优化结果。

## 空间优化增量检查点（已验证）
- 协同增量已提交61d0063。现有优化算法接入真实可执行模型/数据输入/派生场景/工作流/worker与实体结果和界面，见spatial-optimization.md，R31映射已更新。
- core/optimization.py包含CandidateUnit（原domain路径仍可导入）、OptimizationFrame/Outcome/Spec，严格数值/明确单位/可加性/保护清单/不可行null。core.ModelType新增OPTIMIZATION；coastal_catalog合并为24模型，已有23签名不改，主库已幂等init。
- optimization_routes.save通过源场景固定副本+实际S3候选文件+单节点workflow+record FK提交；原场景不变，scope内幂等。run复用统一预检与worker。新scene DELETE归档保护/重复请求已测试。
- 数据声明面积，不从几何编造指标；前端明确可加风险不是概率。运行转换面积与下限为m²，保护优先。结果按实际unit ID绑定固定实体，未匹配明确UNBOUND。
- 领域23项035445935482Z、注册/旧场景30项035920660105Z、API/worker/归档17项040903494975Z、前端42项/类型/lint/构建/契约漂移041506722091Z通过。真实浏览器041708536006Z通过：预算3选U3/收益8/成本3/40000m²、预算0不可行，两个结果均绑定3个真实版本实体，截图已查看。
- 完整后端354项：20260921T041838897503Z-optimization-backend-full；全浏览器18条：20260921T041839375285Z-optimization-browser-full，同源代码保持不变，全部通过。当前无验收进程。API88450/worker38305已加载本轮24模型，beat28693不变。
- 下一模块第43节Research Evaluation。尚无独立research/experiment实现。规划账本persistence/planning.py已有PlanningTrace+ProviderRequest真实调用预算/请求审计，不能把预留数当实际调用/token。现有PlanningTrace仅owner可读。外部LLM凭证缺失仍BLOCKED，不重复问、不伪造实验；规则组与统计/UI可继续。

- 科研实现入口补充：可复用现有Job/ResultBundle的租约、取消和真实发布；Job.manifest本身是JSONB，ResearchManifest应有明确kind并独立验证，不能伪造普通WorkflowSpec包装实验。ResultManifest.result_type是Name，可真实标识research_evaluation，无需伪造模型运行。create_queue仅调用runner.run/pending，可按实际manifest类型调度新ResearchWorker，避免造第二套状态机。需要核对Results/RunDetail/重试路径的类型兼容，保持普通workflow不变。
- 研究需求已读第43/44/68节及EQ：A规则、B仅LLM、C LLM+KG+约束；有效率、违规率、人工修订次数、延迟；错误注入binding统计；12项科研验证必须真实执行。生产create_plan对可规则解析任务不调用LLM，因此科研B/C不能假称allow_external等于真实调用。core.llm和persistence.planning保存真实请求预算/dispatch/usage，需复用。外部凭证缺失继续BLOCKED。

## Research foundation checkpoint (in progress)
- Resumed from 8e6bf12; prior model/data work already committed and superseded. No duplicate implementation. API/worker/beat restarted as PIDs 28970/28971/28972; logs artifacts/logs/{api,worker,beat}-research-resume.log. /health/ready confirms database/storage/queue ready.
- New core/research.py defines strict observations and explicit denominators; BLOCKED/FAILED not successes, unknown manual edits/tokens stay null, external/mock/replay arms never pooled, duplicate trial identities rejected. Five red/green tests passed (20260921T043748524325Z-research-metrics-green).
- New core/research_planning.py freezes case snapshots and invokes the actual deterministic planner plus shared workflow validation. Valid, missing-data and unrecognized-goal trials tested with prior planner regressions (20260921T043957127321Z-research-rule-green). No candidate execution or external call claimed.
- Research integration remains unfinished: worker Job dispatch, authenticated API, A/B/C provider ledger integration, binding experiments, UI, actual research reports. External credentials remain BLOCKED. Latest source changes uncommitted; no evidence process active after the green run.


## 真实影像与本地 Qwen 检查点（进行中）
- 用户确认清理范围是界面合成样例与测试记录，保留自动化测试和历史证据；尚未清理。计划可逆归档，保护历史引用。
- 黄河口、胶州湾、长江口两期 Sentinel-2 L2A 已真实下载 AOI，来源/采集时刻/校准/质量掩膜/SHA 保存在 artifacts/runtime/real-imagery；获取证据045653853670Z通过。三个完整场景尚未发布，不计完成。
- NDVI/NDWI 可信组件通过050600327568Z局部检查；正在补齐瞬时采集约束、生产注册、场景影像显示与真实执行。
- OSM/NASA 在线底图控件已通过前端静态与单元检查（044846122894Z），真实浏览器网络显示待验证。
- 本机 Ollama Qwen 结构化真实调用通过045741753235Z：1次请求、提供方返回730 tokens。LOCAL来源，不能计为外部云实验或完整 B/C 对照。私有配置已保存，服务重启后加载。
- 专门管理员界面尚未实现，已有管理员账户与服务端管理API。全范围任务仍未完成。

## 校准核查发现（必须优先修复）
- 381项全后端回归通过053253396825Z，但真实影像首轮虽任务SUCCEEDED，科学复查发现legacy sentinel-2-l2a元数据歧义，不能作为通过的科学示范。黄河口/胶州湾有效像元异常少。旧真实项目9bdf974b-5ad4-5245-a8cd-c9420690f64b需保留并隔离，不能覆盖旧结果。
- 已探测同日同轨 Collection 1 产品，COG内部scale=.0001、offset=-.1与STAC一致；旧COG内部1/0，STAC却是.0001/-.1且boa_offset_applied=true。提供方issue71有相同异常。改用元数据一致的Collection1，加入不一致拒绝测试，再独立核算。
- 旧真实浏览器测试053228095206Z失败因导航到场景详情而非/workspace；需要修正测试入口，不是图像网络通过。
- 当前API/worker/beat PID33289/33304/33314，日志*-real-imagery.log。新前端已构建；尚未完成清理。

## Collection 1 与管理员清理验收（2026-09-21）
- 校准冲突已修复：强制STAC与COG校准一致，改用同日同轨Collection 1；旧项目模型禁用并可逆归档，旧数据与结果保留。接受项目f597ad33-e6bd-585e-b5a0-3a347cb16e19有3真实场景、13资产和3成功结果。
- 获取054037882670Z、真实API/独立worker及原始DN逐像元独立核算054321509734Z通过。黄河口110142、胶州湾128712、长江口15031个有效像元，数值最大误差0，运行LLM调用均0。artifacts/research/real-imagery-crosscheck.json保存统计。
- 真实浏览器054635635924Z通过三场景/三结果/双期切换和OSM、NASA实际HTTP200，六张截图。最新结果边界透明修改尚待重测。
- 管理界面已实现账号、全局权限、项目成员、项目可逆归档、审计记录；前端46项/类型/lint/构建055506957043Z通过，归档数据库及API回归5项通过055248182895Z的后端子命令（该复合命令随后因前端测试失败，不能将整项记PASS）。
- 0007迁移主库完成；API已安全重启PID35880，日志api-admin.log；worker33304、beat33314仍运行。060227416896Z-admin-cleanup-live真实浏览器PASS：合成项目与错误校准旧项目归档→恢复→再次归档，历史统计未改变，默认工作区仅3个真实场景。
- 当前正在隔离全部普通E2E：临时数据库/存储桶/队列/端口，不再往用户项目写测试记录；真实影像和显式管理员清理移入acceptance目录，测试保留。首次入口Path.open参数错误已保留失败证据并修正，正在重跑。
- 静态质量060554240027Z通过；新增数据库选择与禁用LLM回归060515956338Z通过。全范围任务仍未完成，研究执行/UI、覆盖率等缺口保持有效。

- 隔离普通浏览器回归060653925751Z通过18/18，随机测试数据库/桶/队列/进程已清理，日志保留；用户默认工作区未被写入。清理后的真实影像浏览器061033358630Z通过，最新透明边界截图已查看。空STAC快照目录061111733480Z从互联网成功取得4个固定Collection 1产品，干净安装入口已补全。正在跑全后端，不能提前记通过。

- 061021803379Z-imagery-admin-backend-full：390 passed，11项依赖/显示产品警告保留；061323492550Z契约漂移、46前端测试及生产构建通过。无验收进程运行。本轮集中自查已查看影像权限/校准、管理员归档与独立E2E资源清理路径；这不是全范围最终审查。下一步继续research真实provider/worker/API/UI，不能宣称全任务完成。
