# CoastMAS V3 全系统实现差距审计

审计日期：2026-09-25。审计前 commit：`8d8ae10e8a53c3aa63501c0244b7e37739609c13`（GitHub main已读回核对）。这是诊断交付，**没有修复产品业务代码，也没有宣布全系统完成**。

## 1. 结论与事实基线

当前系统已有可运行的数据接入、持久研究现场、8个内置指标核函数、部分评价/空间处理、真实地图产物、管理目录及规划版本基础。**完整V3的ModelOps、一般Coupler、Simulation、Planning编译—候选—再评价、Comparison八步与横切平台尚未交付。**

- V3十个一级中心已在实际Shell；54项导航配置中只有17个可导航链接，其余37项不是可用业务。项目CRUD在“项目与研究→项目”，并非两套项目数据源。
- 32个步骤都实际打开，17个步骤为明确未接通状态；已接通步骤也只按已测范围计分，不因按钮可点而视为完整。
- 177项能力逐项映射；状态计数：`{"PARTIAL": 40, "MISSING": 79, "VERIFIED": 1, "REGISTERED_ONLY": 54, "BLOCKED": 3}`。这是功能范围覆盖分类，**不计算成完成百分比**。
- 35项问题：`{"P1_MAJOR": 26, "P0_BLOCKER": 2, "P2_NORMAL": 7}`。最先处理可复现下载/错误链及阻断的ModelOps、Planning编译，再修产品职责偏航。
- 正确的数值/权限/事务能力保留；工程缺项不归因于用户资料，未知科学定义不猜填。

### 范围、身份与保护

采用“最新用户裁决→V3后专项→V3.0→master工程细节→旧设计”的优先级。V3 IA和四类任务来自当前明确裁决；没有假称找到未提供的独立V3文件。master结构化177能力/145验收只是范围索引，不是已实现证明。Planning补充、指标内置化及新增平台要求一并核对。

实际服务58013只读；58125使用新SQLite及合成工程夹具，读取同一`master-v3-dev25`前端包。58012、原data_quan、模型原包、正式账号和历史数据库没有修改。没有服务替换。原始业务数据正式科学结论本轮未复验，不能用本轮小夹具代替。

[环境基线](../../.review/evidence/runs/v3-audit-20260925/baseline.json)；[构建字节对照](../../.review/evidence/runs/v3-audit-20260925/bundle-identity.json)：服务7个JS/CSS与本轮从审计commit隔离构建完全相同，58013/58125首页SHA也相同。145条实际OpenAPI路径、46张已加载表、174个源码路由声明（包含同路径多method）见[可达性索引](../../.review/evidence/runs/v3-audit-20260925/source-index.json)。原始`routes.json`因框架惰性路由枚举仅得到直接路由，不作为完整API清单。

## 2. 实测与证据层级

| 实际检查 | 结果 | 证据及边界 |
|---|---|---|
| 当前next后端 | PASS | [290项](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)；含真实数值/数据库/worker组件测试，部分故障注入，不冒充290条浏览器E2E |
| 前端组件 | PASS | [72项](../../.review/evidence/runs/v3-audit-20260925/frontend-tests.json) |
| lint、类型、隔离构建 | PASS | [lint](../../.review/evidence/runs/v3-audit-20260925/lint.log)、[类型](../../.review/evidence/runs/v3-audit-20260925/typecheck.log)、[构建](../../.review/evidence/runs/v3-audit-20260925/build.log)；大包/依赖警告保留 |
| 管理、导入恢复、规划版本、方法发布应用、NDVI、规划单元六条浏览器链 | PASS | [最终同批6/6通过](../../.review/evidence/runs/v3-audit-20260925/final-regression.log)，[隔离范围核对](../../.review/evidence/runs/v3-audit-20260925/isolation-check.json)；[首轮3通过1失败](../../.review/evidence/runs/v3-audit-20260925/regression.log)、[修正探针后的方法链](../../.review/evidence/runs/v3-audit-20260925/method-corrected.log)、[两条真实空间链](../../.review/evidence/runs/v3-audit-20260925/spatial.log)。原定位器/跳转失败保留，不记产品修复 |
| 六光谱指标实际worker数值 | PASS | [文件哈希和原值](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)；原始API脚本的6个FAIL来自随后旧下载路径，未抹掉 |
| 旧单项成果下载 | FAIL | 同上，6个/files/0均500；主成果下载200且hash匹配 |
| 指标Coupler四种匹配 | PASS | ready、缺NIR、物理量不适用、两期网格合法适配建议；不是一般模型耦合验收 |
| 运行中取消 | PASS | [实际事件序列](../../.review/evidence/runs/v3-audit-20260925/job-cancel-corrected.json)：202→running→取消标志→worker确认cancelled，无output/result409；仍不满足新FSM/SSE合同 |
| 权限与并发 | PASS | [实际API拒绝](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)、[双浏览器412差异](../../.review/evidence/runs/v3-audit-20260925/regression/planning-objects.json)、[普通账号页面拒绝](../../.review/evidence/runs/v3-audit-20260925/final-browser-corrected.json)；不代表RLS或空间编辑已实现 |
| 当前全部业务E2E、真实模型上传、全Planning/Simulation | BLOCKED | 当前工程缺项，不是等待例行确认 |
| 大文件负载/全量实际业务、恶意脚本容器实验、远端真实服务、完整复现/不确定性 | NOT_RUN | 无适用当前完整链或本轮未做专项负载/攻击执行；源码安全配置不替代实测 |

证据标签：EXECUTED_AND_SOURCE为实际动作＋源码；SOURCE_CONFIRMED为可达源码/契约；DOC_ONLY为历史声明；INFERENCE/NOT_TESTED明确未证实。机器清单保留探针修正记录。新审计不覆盖旧日志，也不因旧PASS而判断新能力完成。

## 3. 导入、声明与错误追踪

| 路径 | 实际操作/持久化 | 状态 |
|---|---|---|
| 资料库选择 | 正确定位带文件名按钮后，原任务input 1→2，真实事务绑定 | WORKING |
| GeoTIFF | UI接入→真实资产/版本→绑定→原生预览；不填任务科学定义 | WORKING |
| 多文件/半批失败 | good.csv入库绑定，broken.bin保留失败；拖放可继续 | WORKING |
| 文件夹 | 两CSV一次目录选择，绑定两项，未造第二顶层任务 | WORKING |
| CSV | API/UI预览、严格列数检查；未伪造地理位置 | WORKING |
| Shapefile组合 | ZIP主附件真实GDAL读取；裸多文件归组仅组件层测试，未再跑浏览器 | WORKING（ZIP）/NOT_TESTED（裸组包UI） |
| 已授权来源 | 新目录grant→用户显式选文件→worker受管快照→绑定 | WORKING |
| 已有Task Result | stage_products成为实际asset；已有指标直接引用有真实组件测试；Assessment→Planning起点尚缺 | PARTIAL |
| 主件附件复用/并发冲突/幂等 | 93B孤立TFW关联受管原件，不重传主件；冲突保留已入库资产并恢复绑定 | WORKING |

来源声明不是一律强制填：无输入不渲染；字段折叠，已有模板按hash/范围/期限复用，单位冲突不覆盖文件事实。应继续保留后台严谨性，补充metadata/source grant/provenance的适用信息读取次序；按本次动作缺失才提示（AUDIT-026）。

**原截图中的两段错误**：`onPreview`先保存个人视图，失败被`useViewState`记录，再被`ImportPanel`拼为“资料已加入研究；预览或视图保存失败：…”；422默认`detail`没有被前端正确消费，成为“请求校验失败，请检查输入”。本轮自然上传未触发同样422；在隔离浏览器仅将一次真实请求的band改为0后，服务器实际返回422、资产和绑定仍成功。截图显示一条合成错误及顶部保存失败，**没有证据断言始终有两个独立Banner，也不知道原截图具体无效字段**。建议统一错误对象、保留事务部分成功，提供恢复视图动作。见[受控故障页面](../../.review/evidence/screenshots/v3-audit-20260925/partial-success-double-error.png)。

### 代表性错误与主要操作覆盖

| 页面/动作 | HTTP/后端code | 当前呈现、根因与恢复 |
|---|---|---|
| API新建空标题 | 422，无业务code | 默认Pydantic detail未规范化；普通UI有名称约束，API直测不冒充界面失败 |
| 导入后视图band=0 | 422，无业务code | 真实字段错误丢失，显示“资料已加入研究；预览或视图保存失败：请求校验失败，请检查输入”；无定向恢复，不该重传 |
| 旧研究revision保存 | 409 / DRAFT_CONFLICT | 真实冲突，保留编辑并提供比较；尚未统一成412 |
| 两浏览器修改规划目标 | 412 | base/server/proposed差异可见且可处理，最终隔离链通过 |
| 旧单项下载 | 500，无业务code | KeyError media_type；直接链接Internal Server Error，主Artifact路径另行可用 |

机器版`representative_errors`逐项定位证据。原始[66项操作记录](../../.review/evidence/runs/v3-audit-20260925/browser.json)区分WORKING与探针失败，后续纠正引用不覆盖原记录。[最终六链](../../.review/evidence/runs/v3-audit-20260925/final-regression.json)覆盖新建、保存、编辑、选择、加入、导入、发布、明确应用、计算、查看、原生点查、主导出、移出/恢复、批量回收/恢复及并发处理；[取消](../../.review/evidence/runs/v3-audit-20260925/job-cancel-corrected.json)单独实际验证。导入绑定冲突恢复通过不等于失败Job重试/checkpoint已验证；缺失ModelOps/比较/规划阶段为DEAD_END或PLACEHOLDER，不能当WORKING。未执行全站每个弹窗每个控件组合，详见NOT_RUN边界。

## 4. 算法、模型、规划和版本结论

- NDVI UI只选择指标即可，自动真实RED/NIR匹配、202、固定recipe/算法/参数版本、真实栅格/点查/主下载通过。六光谱核函数在实际worker分别执行；非法像元保留mask，未填0冒充观测。道路密度/扩张速度有真实组件测试，本轮不虚报逐项UI链。
- 方法草稿→发布→批准→明确应用、克隆、CSV导入及缺失依据保留有实际浏览器证据。但其“指标库”与普通内置recipe库割裂；权重步骤也没有普通用户直接选择AHP/Entropy/CRITIC的完整体验。
- AHP、Entropy、CRITIC、手工、WLC、TOPSIS、PCA、Fisher-Jenks实际数值执行；typed输出可防止PCA冒充WeightSet。评价型PP未接通，PPCI聚类/PPR回归不能替代。
- 当前模型目录为空；已准备简单Python模型但入口缺失，完整上传链在第一个动作即阻断。没有运行未验证用户代码。旧Docker runner有non-root/no-network/readonly/cpu/memory/pids配置，但本轮未做恶意循环/逃逸实测，不能填SANDBOX专项PASS。
- 独立ObjectiveSet/ConstraintSet/DecisionSpec有自己的版本/成员，不依赖先创建PlanningProblem；双浏览器412、发布及显式应用已验证。单元准备实际输出矢量、原生点查、恢复和hash下载通过。诊断、问题编译、候选、反事实再评价、V3比较链未完成；现有MILP/Pareto数值通过不等于业务求解可用。
- 比较后台已有不可比即阻断、单位一致化、固定父manifest/bundle、权重/约束敏感性；V3七个配置步骤没有连接。跨不同ClassScheme的转移矩阵无完整实现，不能靠不同比较结果数组做等级变化。Pareto保留多个候选而不自动选优的核函数测试通过。
- 实際RunManifest只证明当前快照，不含全部新版合同；没有Reproduce/ProvenanceGraph/SSE/FeatureRevision/EditLease/U2-U3平台链。unknown未被本轮输出伪装成概率0，但“不生成假概率”不等于不确定性平台完成。

## 5. 标准与版本支持

| 档案 | 识别/校验/语义 | 任务/映射与导出 | 限制与反例证据 |
|---|---|---|---|
| GeoTIFF/COG | CRS/transform/band/scale/offset/mask真实读取 | 栅格处理/原生点查/实际TIFF输出 | COG读取不保证所有输出都是COG；错CRS/NoData/合法零测试见test_geospatial_view/test_asset_identity |
| GeoJSON RFC7946 | 实际几何与属性，源/显示定位分开 | UnitSet/矢量结果/GeoJSON下载 | 纬度越界/无几何/重复ID/重叠单元反例；未做跨日期线完整专项 |
| Shapefile/GPKG | 主附件及多图层读取；GPKG记录容器版本 | 矢量字段/原生几何参与单元生成 | 缺附件/越界ZIP反例；不保证所有格式往返无损 |
| CSV/CSVW | 方言编码、列数；CSVW保留字段语义/单位 | 表格计算/声明复用；CSV结果 | CSV不是自动年鉴理解；复杂多级表头与全部行政关联未做完 |
| NetCDF CF 1.7—1.12 | 指定版本、calendar/cell_methods/time bounds | 一维时间适配及结果固定单位 | 不泛化为网格/mesh动态耦合；未知版本/不合法累积及插值反例有测试 |
| STAC | JSON文档版本识别 | 未完成item→授权远端资产→任务/导出链 | 上传STAC文档不代表数据已接入 |
| OGC API Processes | 有真实任务引用执行/状态/结果协议 | 与现有jobs连接，组件正反例 | 不是成果服务发布，也不是任意远端协议/全部一致性认证 |

逐阶段范围依据profiles/csvw/temporal/process_service源码及本轮290项测试；没有外部认证结论。

## 6. 桌面视觉与交互

已查看真实截图：最终稳定NDVI栅格、原生规划多边形、方法误导入口、Coupler目录、导入部分成功、管理及规划冲突。底图属外部网络结果，未以其可用性替代科研栅格。

| 视口 | 地图top | 地图高 | 全页溢出 | 证据 |
|---|---:|---:|---|---|
| 1440×900 | 121 | 774 | 无 | [截图](../../.review/evidence/screenshots/v3-audit-20260925/settled-result-1440.png) |
| 1366×768 | 121 | 642 | 无 | [截图](../../.review/evidence/screenshots/v3-audit-20260925/settled-result-1366.png) |
| 1920×1080 | 121 | 954 | 无 | [截图](../../.review/evidence/screenshots/v3-audit-20260925/settled-result-1920.png) |
| 2560×1440 | 121 | 1314 | 无 | [截图](../../.review/evidence/screenshots/v3-audit-20260925/settled-result-2560.png) |

字号13px；完整中文左菜单、72px步骤栏、互斥右面板与底部目录均保留。信息密度/按钮层级/Modal/表格/Inspector/Dock/步骤栏/地图占比/字色/图标/控件/空白已按上述截图评估：当前成果主区紧凑，不需要再次大改Shell；主要问题是缺业务、目录标题旧、导入Modal长说明、工程“待核查”泛用，以及首次绘制/截图时序。移动端不是本轮目标。复杂AHP矩阵、未接通模型/规划/比较页无可测完整UI，键盘全站逐控件与30层压力未完整执行，记NOT_TESTED。

初版workspace四张截图捕获了加载态，不能据此判地图故障或验收通过。首次NDVI1440截图白底但后续渲染/稳定截图有实际颜色，当前可视功能可用，测试等待条件需整改；旧透明度偶发失败本轮未复现，仍保留追踪而不是宣布修复。

## 7. 性能与安全边界

已确认有栅格显示缓存、原生有界预览、目录分页、chunk upload预算及worker产物原子提交。风险集中在同步时间预检、向量全量扫描、指标全库候选组合、整数组JSON输出及大前端包；未进行生产容量/SLO测试。不能把100000要素/小型矩阵预算写成无限全域。

本轮真实API证明普通用户只读、成员撤销生效、系统管理员不因身份自动获得其他项目科学数据；管理UI创建不自动加入项目，最后管理员/负责人组件反例保留。source grant撤销组件测试、文件hash/路径边界测试通过。数据库RLS、恶意用户代码容器对抗、远端重复付费防护、私有预签名URL专项未验证或未实现。源码未发现active next裸exec/eval上传代码，不对整个历史仓库作绝对无漏洞结论。

## 8. 问题明细

以下每项都包含要求、事实、位置、证据、根因、严重度、影响、建议及依赖。建议不是本轮已实施。

### AUDIT-001 · V3中心齐全，但54项入口仅17项可进入

- 模块／类型／严重度：信息架构 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：54个既定入口映射真实领域能力；未完成不能当完成
- 当前：10个一级中心已落实；17个链接实测可打开。37个无path项仅注册为development，当前构建隐藏。不是仍停留在旧四组导航。
- 位置：`next/web/src/navigation.ts:29`；`next/web/src/App.tsx`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/browser.json](../../.review/evidence/runs/v3-audit-20260925/browser.json)
- 根因：导航注册先于领域页面交付，实际构建未开启development菜单展示
- 影响：信息架构的完整业务交付或审查可靠性；阻塞下游：是
- 建议：按V3原归属补齐领域目录；开发环境明确未启用；禁止以空页补数。
- 依赖：无；整改Wave 1

### AUDIT-002 · ResearchTopic与TaskRelation未落地

- 模块／类型／严重度：项目与研究 · `DATABASE_MODEL` · `P1_MAJOR`
- 要求：Project → Research Topic → Task及显式任务依赖
- 当前：项目与任务有唯一真源；无研究内容/任务关系路由和专门对象，项目下直接存tasks。
- 位置：`next/src/coastmas_next/store.py`；`next/web/src/navigation.ts:33`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：仍使用project_id直接组织任务
- 影响：项目与研究的完整业务交付或审查可靠性；阻塞下游：是
- 建议：补Topic、TaskRelation及版本/权限；既有Task显式归属，不建重复Project CRUD。
- 依赖：无；整改Wave 1

### AUDIT-003 · 状态变量至情景分析五步未接通

- 模块／类型／严重度：Simulation · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：不同任务有不同可执行八步
- 当前：可创建simulation并恢复草稿，但3—7步明确显示未接通；无模型/情景实际操作链。
- 位置：`next/web/src/taskFlows.ts`；`next/web/src/ResearchStepPanel.tsx:30`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/browser.json](../../.review/evidence/runs/v3-audit-20260925/browser.json)
- 根因：只完成任务类型与步骤配置，未实现相应业务编辑和服务
- 影响：Simulation的完整业务交付或审查可靠性；阻塞下游：是
- 建议：连接状态变量、固定ModelRelease、情景、模拟执行与分析；不要复用评价表单。
- 依赖：AUDIT-010, AUDIT-007；整改Wave 2

### AUDIT-004 · 比较后台存在，V3前七步没有接通

- 模块／类型／严重度：Comparison · `BROKEN_INTERACTION` · `P1_MAJOR`
- 要求：比较任务应选择固定成果并进行口径、统计、差异和敏感性分析
- 当前：comparison可创建；前七步未接通。comparison.py及比较执行/打包存在并有实际后端测试，旧ComparisonTask不属于当前主路由。
- 位置：`next/web/src/ResearchStepPanel.tsx:30`；`next/web/src/App.tsx`；`next/src/coastmas_next/comparison.py`；`next/src/coastmas_next/comparison_tasks.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/browser.json](../../.review/evidence/runs/v3-audit-20260925/browser.json)、[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)
- 根因：V3工作台与旧独立比较编辑器未连接
- 影响：Comparison的完整业务交付或审查可靠性；阻塞下游：是
- 建议：复用可比性门禁与固定父结果，补七步UI和比较bundle，不将算法缺口包装为无资料。
- 依赖：AUDIT-016；整改Wave 1

### AUDIT-005 · 内置赋权/降维核函数未成为普通任务的直接方法选择

- 模块／类型／严重度：指标与方法 · `BUSINESS_LOGIC` · `P1_MAJOR`
- 要求：AHP/Entropy/CRITIC直接使用，PCA/PP独立语义
- 当前：19个typed operators有实现。AHP/熵权/CRITIC/PCA/WLC/TOPSIS/Jenks数值执行成功，PCA不产生WeightSet；普通权重步骤仍进入MethodSelector，依赖方法方案。
- 位置：`next/web/src/ResearchEditor.tsx`；`next/web/src/MethodSelector.tsx`；`next/src/coastmas_next/builtin_operators.py:321`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)、[.review/evidence/runs/v3-audit-20260925/browser.json](../../.review/evidence/runs/v3-audit-20260925/browser.json)
- 根因：BuiltinOperatorRegistry与业务方法选择/阶段产物尚分离
- 影响：指标与方法的完整业务交付或审查可靠性；阻塞下游：是
- 建议：提供按类型分组的系统方法入口；只有AHP展示矩阵；直接计算产出独立WeightSet/ScoreResult/ClassScheme。
- 依赖：AUDIT-006；整改Wave 1

### AUDIT-006 · ARCHITECTURE_DRIFT：方法编辑中的指标库仍是已批准定义库

- 模块／类型／严重度：指标与方法 · `IA_DRIFT` · `P1_MAJOR`
- 要求：普通用户选择系统内置可执行指标，不先创建批准IndicatorDefinition
- 当前：工作台IndicatorSelector正常使用内置定义；方法编辑“从指标库选择”实际查询项目已批准科学定义，空项目显示“项目内尚无已批准的指标定义”。
- 位置：`next/web/src/MethodCatalog.tsx:533`；`next/src/coastmas_next/method_library.py:426`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/supplement-browser.json](../../.review/evidence/runs/v3-audit-20260925/supplement-browser.json)、[.review/evidence/screenshots/v3-audit-20260925/method-indicator-definition-drift.png](../../.review/evidence/screenshots/v3-audit-20260925/method-indicator-definition-drift.png)
- 根因：两个指标真义入口分别指向可执行recipe与旧语义模板
- 影响：指标与方法的完整业务交付或审查可靠性；阻塞下游：是
- 建议：统一用户选择入口，科学评分方向/阈值仍由适用方法明确；维护模式单独管理技术定义。
- 依赖：无；整改Wave 1

### AUDIT-007 · 数据—模型匹配页面实为任务列表＋预检

- 模块／类型／严重度：耦合与工作流 · `IA_DRIFT` · `P1_MAJOR`
- 要求：独立DataMatcher/Adapter/SceneConstraint/WorkflowComposer/Orchestrator
- 当前：点击核对匹配只GET tasks/{id}/preflight。指标匹配器已真实支持ready/missing/inapplicable/adaptation；尚无一般模型契约选择、适配路径图、多模型工作流。
- 位置：`next/web/src/DomainDirectory.tsx:22`；`next/src/coastmas_next/indicator_matching.py`；`next/src/coastmas_next/matcher_diagnostics.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/supplement-browser.json](../../.review/evidence/runs/v3-audit-20260925/supplement-browser.json)、[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)、[.review/evidence/screenshots/v3-audit-20260925/coupler-task-preflight.png](../../.review/evidence/screenshots/v3-audit-20260925/coupler-task-preflight.png)
- 根因：用整任务执行前检查承接独立Coupler职责
- 影响：耦合与工作流的完整业务交付或审查可靠性；阻塞下游：是
- 建议：复用诊断结构，按DataProfile/ModelContract执行硬门禁和合法Adapter路径，补版本化工作流与场景约束。
- 依赖：AUDIT-010；整改Wave 1

### AUDIT-008 · 62项内置定义中54项未安装

- 模块／类型／严重度：指标库 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：发布指标必须有实际算法、固定版本与测试
- 当前：8项published：NDVI/EVI/SAVI/NDWI/MNDWI/NDBI/道路密度/城市扩张速度；其余54项not_installed，未伪装为可计算。六个光谱指标真实worker产物数值通过；道路/扩张有组件/API测试，未逐项浏览器验收。
- 位置：`next/src/coastmas_next/builtin_indicators.json`；`next/src/coastmas_next/indicator_registry.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)、[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)
- 根因：目录先注册，生态/社会/灾害/海岸多数生产recipe未实现
- 影响：指标库的完整业务交付或审查可靠性；阻塞下游：是
- 建议：逐项实现有依据的recipe/数据匹配/默认业务参数/正反例；保持未安装不可算，不用名字注册冒充能力。
- 依赖：AUDIT-018, AUDIT-019；整改Wave 2

### AUDIT-009 · 自定义公式/Python/R/AI指标发布链缺失

- 模块／类型／严重度：指标维护 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：维护权限、受限公式DSL、扫描/依赖/沙箱/数值验证/人工发布
- 当前：没有自定义指标维护API/UI/验证发布记录；普通指标页不能上传即运行，当前未发现active next中的任意eval/exec。
- 位置：`next/src/coastmas_next/indicator_service.py`；`next/src/coastmas_next/indicator_registry.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：内置静态registry尚未扩展为受控发布系统
- 影响：指标维护的完整业务交付或审查可靠性；阻塞下游：是
- 建议：建立受限表达式与维护发布链；复用ModelOps沙箱，不在API进程执行用户代码。
- 依赖：AUDIT-010, AUDIT-022；整改Wave 2

### AUDIT-010 · 简单Python模型在上传第一步即无真实入口

- 模块／类型／严重度：模型工程 · `MISSING_IMPLEMENTATION` · `P0_BLOCKER`
- 要求：upload→static parse→contract→sandbox validation→publish→use
- 当前：OpenAPI仅模型目录、批准、撤销三条模型路径；无上传、解析、解构、ModelContract、测试及版本管理。工程simple_model.py已准备，但无合法入口可提交；未强行当数据导入。
- 位置：`next/src/coastmas_next/models.py:22`；`next/web/src/DomainDirectory.tsx:9`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)、[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：Release限制为两种预配置R模型，通用ModelOps未建立
- 影响：模型工程的完整业务交付或审查可靠性；阻塞下游：是
- 建议：在模型工程补完整版本与验证流水线；用户代码经队列/独立沙箱，固定可重复运行包。
- 依赖：无；整改Wave 0

### AUDIT-011 · 当前58013模型目录为空

- 模块／类型／严重度：模型运行环境 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：已提供模型经当前环境验证后可批准使用
- 当前：live配置无runtime_catalog，同配置隔离实例GET models=[]。旧仓库有PPCI/PPR及Docker适配器，不能据此宣布当前运行可执行；本轮未重跑原模型包。
- 位置：`next/src/coastmas_next/models.py:60`；`next/src/coastmas_next/config.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/baseline.json](../../.review/evidence/runs/v3-audit-20260925/baseline.json)、[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)
- 根因：当前部署未装载核验运行目录，旧证据不是当前执行资格
- 影响：模型运行环境的完整业务交付或审查可靠性；阻塞下游：是
- 建议：通过新的ModelOps接入实际原包并重验，恢复版本限定的项目批准；不得默认为latest。
- 依赖：AUDIT-010；整改Wave 2

### AUDIT-012 · PlanningProblemCompiler未实现，所有V3规划提交被阻断

- 模块／类型／严重度：Planning · `MISSING_IMPLEMENTATION` · `P0_BLOCKER`
- 要求：版本对象→问题编译→真实求解→Candidate→再评价
- 当前：独立目标/约束/决策/UnitSet可保存发布和使用；预检始终给PLANNING_COMPILER_NOT_READY。真实MILP/Pareto核函数未接入该任务。
- 位置：`next/src/coastmas_next/execution.py:124`；`next/src/coastmas_next/planning_solver_v1.py:150`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)、[.review/evidence/runs/v3-audit-20260925/regression/planning-objects.json](../../.review/evidence/runs/v3-audit-20260925/regression/planning-objects.json)、[.review/evidence/runs/v3-audit-20260925/spatial/planning-units-flow.json](../../.review/evidence/runs/v3-audit-20260925/spatial/planning-units-flow.json)
- 根因：版本对象、空间单元与求解器之间缺编译和执行契约
- 影响：Planning的完整业务交付或审查可靠性；阻塞下游：是
- 建议：固定Scenario/UnitSet/目标约束系数，编译合法问题，队列运行及独立约束校验；不得套旧加权评分优化。
- 依赖：AUDIT-013, AUDIT-015；整改Wave 0

### AUDIT-013 · 诊断、Scenario、CandidateState、再评价与比较报告缺失

- 模块／类型／严重度：Planning · `DATABASE_MODEL` · `P1_MAJOR`
- 要求：Assessment→Diagnosis→Planning→Candidate→Re-Assessment→Comparison
- 当前：无DiagnosisRecipe/DiagnosisVersion/ScenarioVersion/PlanCandidate/PlanEvaluation专门持久对象及路径。仅单元准备与配置发布可用。
- 位置：`next/src/coastmas_next/planning_versions.py`；`next/src/coastmas_next/planning_units.py`；`next/src/coastmas_next/planning_recipes.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/browser.json](../../.review/evidence/runs/v3-audit-20260925/browser.json)
- 根因：规划中段领域模型未完成，不是缺少用户科学资料
- 影响：Planning的完整业务交付或审查可靠性；阻塞下游：是
- 建议：实现诊断和情景/候选不可变对象，差分数据引用、再评价冻结及比较报告。
- 依赖：AUDIT-016；整改Wave 2

### AUDIT-014 · Assessment Result进入Planning的显式引用链未接通

- 模块／类型／严重度：Planning与成果 · `BROKEN_INTERACTION` · `P1_MAJOR`
- 要求：已有固定Result直接进入规划，不下载重传、不混最新
- 当前：阶段产物可作为受管asset；原生UnitSet可准备。但没有从Assessment Result建立Diagnosis/Planning的操作与完整来源链接。
- 位置：`next/src/coastmas_next/stage_products.py`；`next/web/src/ResultArtifact.tsx`；`next/src/coastmas_next/planning_units.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)
- 根因：一般资产复用不等于规划反事实基线引用
- 影响：Planning与成果的完整业务交付或审查可靠性；阻塞下游：是
- 建议：提供固定Result→规划起点，保留版本、指标贡献和结果空间身份；重评不得覆写基准。
- 依赖：AUDIT-012, AUDIT-013；整改Wave 2

### AUDIT-015 · 目标/约束/决策范围有限，SolverRegistry未接通

- 模块／类型／严重度：Planning目录与求解 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：按补充规划范围提供适用目标、约束与决策/求解器
- 当前：4个加性目标、3种约束、3种二元决策模板；MILP/最多18单元精确Pareto核函数真实且不自动选最佳，但无一般SolverRegistry、完整多用途/网络/量子等适配。
- 位置：`next/src/coastmas_next/planning_recipes.py:12`；`next/src/coastmas_next/planning_solver_v1.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)
- 根因：当前是有边界的二元配置基础，不是全规划算法平台
- 影响：Planning目录与求解的完整业务交付或审查可靠性；阻塞下游：是
- 建议：按问题类型注册求解能力与规模约束；外部求解器无授权时明确阻塞，先完成本地全域参考。
- 依赖：无（SolverRegistry基础先于ProblemCompiler）；整改Wave 2

### AUDIT-016 · RunManifest/ProvenanceGraph不完整

- 模块／类型／严重度：成果与运行 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：冻结全部适用输入/算法/适配/工作流/规划/环境/锁/产物并可反查
- 当前：实际manifest含输入哈希、draft_revision、recipe/算法/默认参数版本、运行方法和输出网格；输出文件另有SHA。无完整WorkflowVersion/Adapter版本、依赖锁digest/git/environment以及可遍历ProvenanceGraph。
- 位置：`next/src/coastmas_next/execution.py:266`；`next/src/coastmas_next/worker.py:164`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)、[.review/evidence/runs/v3-audit-20260925/spatial/indicator-flow.json](../../.review/evidence/runs/v3-audit-20260925/spatial/indicator-flow.json)
- 根因：现有任务快照不是全链RunManifest规范
- 影响：成果与运行的完整业务交付或审查可靠性；阻塞下游：是
- 建议：将现有固定快照补为明确适用/不适用的不可变manifest，并在Run/Result详情提供可遍历血缘。
- 依赖：无；整改Wave 1

### AUDIT-017 · 缺少按原配置重新运行及复现等级

- 模块／类型／严重度：成果复现 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：不升级旧输入/算法；缺版本blocked；区分exact/numerical/scientific/external
- 当前：未发现reproduce路由/UI或旧算法版本解析执行器。J项只证明选择不改旧manifest，不能证明算法升级后旧Run可重跑。
- 位置：`next/src/coastmas_next/indicator_registry.py`；`next/src/coastmas_next/execution.py`；`next/web/src/ResultArtifact.tsx`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)
- 根因：只冻结算法身份，未提供历史实现包获取与replay解析
- 影响：成果复现的完整业务交付或审查可靠性；阻塞下游：是
- 建议：按manifest解析全部版本、预定义容差；拒绝静默latest；验证旧版本消失、升级和随机seed。
- 依赖：AUDIT-016, AUDIT-010；整改Wave 2

### AUDIT-018 · 数据准备22项仅部分可达

- 模块／类型／严重度：基础GIS · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：空间准备为可执行工具，不靠手工构造内部输入
- 当前：active支持参考栅格对齐/连续或类别重采样、有效mask、原生几何/单位/时间处理；无完整裁剪、镶嵌、栅矢转换、连接、缓冲/距离/分区统计等V3阶段服务。旧库中的核函数不能算当前任务入口。
- 位置：`next/src/coastmas_next/spatial.py:20`；`next/src/coastmas_next/preparation.py:20`；`next/src/coastmas_next/research_workspace.py:74`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)
- 根因：处理节点operator白名单只有少量算子，Coupler无一般适配规划
- 影响：基础GIS的完整业务交付或审查可靠性；阻塞下游：是
- 建议：按标准profile补共享算子与真实产物，语义保持转换自动化；不改变GridSpec精度声明。
- 依赖：AUDIT-007；整改Wave 2

### AUDIT-019 · CSV识别不等于五种统计空间化服务

- 模块／类型／严重度：年鉴空间化 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：年鉴解析→行政关联/面积/先验/回归/产业空间化→下游指标
- 当前：csv_facts能识别方言、列数与有界预览；无完整宽长年鉴语义映射、五种空间化服务/界面。坐标CSV点图不等于行政统计空间化。
- 位置：`next/src/coastmas_next/profiles.py:260`；`next/src/coastmas_next/observation_space.py`；`next/web/src/ResearchEditor.tsx`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)
- 根因：通用CSV资产读取未接上统计口径和守恒分配业务
- 影响：年鉴空间化的完整业务交付或审查可靠性；阻塞下游：是
- 建议：按实际表头/年份/行政码形成映射，确定性读取复用，保留总量守恒与独立精度区别。
- 依赖：AUDIT-018；整改Wave 2

### AUDIT-020 · 取消语义有效，但统一状态机和SSE缺失

- 模块／类型／严重度：异步运行 · `API_CONTRACT` · `P1_MAJOR`
- 要求：统一queued/preparing/running/cancel_requested/canceled等与有序SSE
- 当前：实际202返回约0.006秒；运行中取消先running+cancel_requested=true，worker确认后cancelled且无输出。无SSE/sequence/progress事件；前端轮询，状态名仍旧契约。
- 位置：`next/src/coastmas_next/execution.py:321`；`next/src/coastmas_next/worker.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/job-cancel-corrected.json](../../.review/evidence/runs/v3-audit-20260925/job-cancel-corrected.json)、[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：布尔取消标记和轮询未升级统一JobStateMachine/事件流
- 影响：异步运行的完整业务交付或审查可靠性；阻塞下游：是
- 建议：保留真实确认过程，补单调事件序列、未知total=null、SSE重连及cancel状态；不得点击即伪造完成。
- 依赖：AUDIT-016；整改Wave 2

### AUDIT-021 · 无checkpoint与remote_unknown协议

- 模块／类型／严重度：运行恢复 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：支持者实际checkpoint；不支持者完整节点重跑；远端未知不得重复收费提交
- 当前：worker有lease/fencing/原子产物，过期租约组件测试通过；无真实checkpoint恢复/paused/remote_unknown，MILP契约明确checkpoint_supported=false。
- 位置：`next/src/coastmas_next/worker.py`；`next/src/coastmas_next/planning_solver_v1.py:196`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)、[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：租约恢复被实现，算法/远端恢复协议尚缺
- 影响：运行恢复的完整业务交付或审查可靠性；阻塞下游：是
- 建议：区分节点重跑与checkpoint恢复；补远端作业身份查询，未知状态禁止盲重试。
- 依赖：AUDIT-020, AUDIT-010；整改Wave 2

### AUDIT-022 · U0—U3及契约传播框架缺失

- 模块／类型／严重度：科研不确定性 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：有依据的敏感性/概率/情景传播，不猜分布，不把unknown当0
- 当前：存在质量/样本范围与简单比较敏感性；无ModelContract uncertainty字段、Monte Carlo/bootstrap/Ensemble节点传播及mean/std/quantile/stability栅格。未发现伪confidence产物。
- 位置：`next/src/coastmas_next/contracts.py`；`next/src/coastmas_next/comparison.py`；`next/src/coastmas_next/models.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)
- 根因：缺统一不确定性契约和执行框架
- 影响：科研不确定性的完整业务交付或审查可靠性；阻塞下游：是
- 建议：先补unknown来源限制与U1，再按显式分布实施U2/U3及逐量命名；嵌入既有成果/分析/规划中心。
- 依赖：AUDIT-016, AUDIT-007；整改Wave 2

### AUDIT-023 · 412/ETag未覆盖全部对象，空间FeatureRevision/Lease缺失

- 模块／类型／严重度：并发编辑 · `API_CONTRACT` · `P1_MAJOR`
- 要求：所有指定draft用revision/ETag/If-Match，空间冲突可比较
- 当前：规划对象双浏览器冲突412有差异；TaskDraft旧revision返回409 DRAFT_CONFLICT，部分对象为expected_revision JSON；无FeatureRevision/EditLease。
- 位置：`next/src/coastmas_next/planning_versions.py`；`next/src/coastmas_next/store.py`；`next/src/coastmas_next/contracts.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/regression/planning-objects.json](../../.review/evidence/runs/v3-audit-20260925/regression/planning-objects.json)、[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)
- 根因：各阶段分别实现CAS，统一契约与空间版本未完成
- 影响：并发编辑的完整业务交付或审查可靠性；阻塞下游：是
- 建议：复用有效CAS与差异面板，统一412；补要素base/server/proposed和短时lease，保存仍查revision。
- 依赖：AUDIT-002；整改Wave 2

### AUDIT-024 · Pydantic错误丢失字段，预览失败只有笼统提示

- 模块／类型／严重度：错误与导入 · `ERROR_HANDLING` · `P1_MAJOR`
- 要求：错误说明对象/原因/修复；导入成功与预览失败分开
- 当前：真实422返回detail/loc/input；api.ts只读message/details，退化为“请求校验失败，请检查输入”。受控band=0请求复现资料已绑定＋视图保存失败，上栏保存失败；自然导入未自发复现原截图错误。
- 位置：`next/src/coastmas_next/app.py:61`；`next/web/src/api.ts:45`；`next/web/src/ImportPanel.tsx:122`；`next/web/src/useViewState.ts:100`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/supplement-browser.json](../../.review/evidence/runs/v3-audit-20260925/supplement-browser.json)、[.review/evidence/screenshots/v3-audit-20260925/partial-success-double-error.png](../../.review/evidence/screenshots/v3-audit-20260925/partial-success-double-error.png)
- 根因：FastAPI默认error envelope与前端协议不一致；view failure.current阻止后续保存，缺就地恢复动作
- 影响：错误与导入的完整业务交付或审查可靠性；阻塞下游：是
- 建议：统一结构化业务错误并剥离input/框架细节；保留绑定成功收据，提供恢复视图/重试而不是重传。
- 依赖：无；整改Wave 0

### AUDIT-025 · 单项产物链接500：缺media_type

- 模块／类型／严重度：成果下载 · `API_CONTRACT` · `P1_MAJOR`
- 要求：真实成果各下载入口均固定运行并可用
- 当前：六个光谱产物均成功生成且数值/哈希正确；/files/0返回500 KeyError media_type。主成果/artifacts/0/download正常；失败路径仍用于步骤产物和导出里的单项产物。
- 位置：`next/src/coastmas_next/execution.py:432`；`next/web/src/ResearchStepPanel.tsx:374`；`next/web/src/ResultArtifact.tsx:720`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)
- 根因：新产物metadata无media_type，旧下载handler强取该键；测试仅走新下载路径
- 影响：成果下载的完整业务交付或审查可靠性；阻塞下游：是
- 建议：统一到固定Artifact下载契约并校验hash，逐UI链接回归，保留正确主成果与bundle路径。
- 依赖：无；整改Wave 0

### AUDIT-026 · 来源自动读取优先级与最少提示未完整实现

- 模块／类型／严重度：来源声明 · `UX` · `P2_NORMAL`
- 要求：先读取metadata/source grant/provenance/已有许可，当前动作需要才询问
- 当前：可靠影像上传查看无需声明；声明表折叠，不是默认要求全填。已有声明按hash/范围/有效期复用且冲突保留；授权源只是访问授权，未形成通用来源/许可优先读取链。
- 位置：`next/web/src/SourceStatement.tsx:83`；`next/src/coastmas_next/reuse.py:130`；`next/src/coastmas_next/knowledge_authoring.py:90`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)、[.review/evidence/runs/v3-audit-20260925/supplement-browser.json](../../.review/evidence/runs/v3-audit-20260925/supplement-browser.json)
- 根因：文件事实、访问授权、科学声明分离正确，但缺来源可信度优先级和按动作问题聚合
- 影响：来源声明的完整业务交付或审查可靠性；阻塞下游：否
- 建议：KEEP_BACKEND_HIDE_UI：hash/版本/依据；CONDITIONAL_PROMPT：确实缺失且当前动作需要的来源许可时期；REMOVE_FROM_NORMAL_FLOW：重复全表确认。
- 依赖：AUDIT-007；整改Wave 3

### AUDIT-027 · V3数据库对象和RLS尚未交付

- 模块／类型／严重度：数据库与权限 · `DATABASE_MODEL` · `P1_MAJOR`
- 要求：服务端项目隔离与目标PG/RLS/版本约束
- 当前：审计/live为SQLite；46表有真实成员检查，独立系统管理员不可读非成员任务；无数据库RLS策略。未发现本轮跨项目泄露，不能以此证明数据库层隔离。
- 位置：`next/src/coastmas_next/store.py`；`next/src/coastmas_next/schema_upgrades.py`；`next/src/coastmas_next/administration.py`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/followup-corrected.json](../../.review/evidence/runs/v3-audit-20260925/followup-corrected.json)
- 根因：应用层授权已做，但数据库基线和新领域模型仍缺
- 影响：数据库与权限的完整业务交付或审查可靠性；阻塞下游：是
- 建议：规划数据结构统一迁移；对非表主/非超级用户执行RLS负例、连接隔离和恢复，不改为管理员默认读全项目。
- 依赖：AUDIT-002, AUDIT-013；整改Wave 1

### AUDIT-028 · 同步预检实际调用时间计算，向量导入全量遍历

- 模块／类型／严重度：性能 · `PERFORMANCE` · `P2_NORMAL`
- 要求：轻量检查不自动启动昂贵计算，规模有界
- 当前：execution.preflight直接temporal_compute；profiles.vector_facts遍历全层；science.entities构造全列表后按100000预算拒绝。未执行生产级性能压测，不能声称超时必现。
- 位置：`next/src/coastmas_next/execution.py:177`；`next/src/coastmas_next/profiles.py:169`；`next/src/coastmas_next/science.py:35`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：校验/计算共用函数，部分API内执行数据扫描
- 影响：性能的完整业务交付或审查可靠性；阻塞下游：否
- 建议：分离结构校验与异步统计；流式预算检查；按真实大文件记录峰值内存、延时，不截样充全域。
- 依赖：AUDIT-020；整改Wave 5

### AUDIT-029 · 指标匹配全库读取且每定义重复匹配

- 模块／类型／严重度：性能与Coupler · `PERFORMANCE` · `P2_NORMAL`
- 要求：项目复用候选有索引和可解释匹配，不随库大小无界膨胀
- 当前：project_assets加载全部可用资产；catalog对每个定义分别match两次；城市两期资料组合与道路×网格产生组合候选。已有普通目录分页不等于匹配已分页。
- 位置：`next/src/coastmas_next/indicator_matching.py:21`；`next/src/coastmas_next/indicator_service.py:80`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：候选检索与匹配执行未分层，缺角色/时期索引和共享一次结果
- 影响：性能与Coupler的完整业务交付或审查可靠性；阻塞下游：否
- 建议：按输入语义/空间/时期索引过滤，复用匹配结果；保留完整候选分母和真实歧义，不静默截断。
- 依赖：AUDIT-007；整改Wave 5

### AUDIT-030 · 早期截图未等待绘制，canvas存在不等于栅格已呈现

- 模块／类型／严重度：视觉与验证 · `TECH_DEBT` · `P2_NORMAL`
- 要求：实际截图和实际产物确认，不以DOM通过代替视觉
- 当前：同一NDVI回归最早1440截图白底但canvas断言PASS；后续稳定截图四分辨率均见真实栅格。旧透明度失败本轮完整重测通过，根因未关闭。
- 位置：`next/web/e2e/builtin-indicators.spec.ts:46`；`next/web/src/AssetMap.tsx:233`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/spatial/indicator-result-1440.png](../../.review/evidence/runs/v3-audit-20260925/spatial/indicator-result-1440.png)、[.review/evidence/screenshots/v3-audit-20260925/settled-result-1440.png](../../.review/evidence/screenshots/v3-audit-20260925/settled-result-1440.png)、[.review/evidence/runs/v3-audit-20260925/final-browser-corrected.json](../../.review/evidence/runs/v3-audit-20260925/final-browser-corrected.json)、[.review/evidence/runs/v3-audit-20260925/spatial.log](../../.review/evidence/runs/v3-audit-20260925/spatial.log)
- 根因：测试等待组件/状态，未保证WebGL最终帧；旧视图异步保存存在时序风险待定
- 影响：视觉与验证的完整业务交付或审查可靠性；阻塞下游：否
- 建议：增加tile/frame可观测条件和实际像素/稳定画面验证；保留早期失败，不盲更新快照。
- 依赖：无；整改Wave 4

### AUDIT-031 · 历史浏览器测试导航/夹具依赖与状态文档已漂移

- 模块／类型／严重度：测试与证据 · `TECH_DEBT` · `P2_NORMAL`
- 要求：同构建可复核测试；不能继承旧PASS
- 当前：若干原测试仍使用“项目管理/方法方案”等旧菜单、硬编码58013及本机ignored夹具。审计临时适配后六链通过；原失败保留。STATE旧主基线顺序和旧结果不应作为本轮事实。
- 位置：`next/web/e2e/unified-methods.spec.ts`；`next/web/e2e/desktop-management.spec.ts`；`next/STATE.md`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/test-adaptations.json](../../.review/evidence/runs/v3-audit-20260925/test-adaptations.json)、[.review/evidence/runs/v3-audit-20260925/regression.log](../../.review/evidence/runs/v3-audit-20260925/regression.log)、[.review/evidence/runs/v3-audit-20260925/method-corrected.log](../../.review/evidence/runs/v3-audit-20260925/method-corrected.log)
- 根因：业务更名/路由与测试基线未同步，证据读写缺统一新旧区分
- 影响：测试与证据的完整业务交付或审查可靠性；阻塞下游：否
- 建议：用当前权限导航并携带受管工程夹具，测试迁移注明接替关系；审计报告优先记录新证据。
- 依赖：无；整改Wave 3

### AUDIT-032 · 完整报告/科研图件/服务发布缺失

- 模块／类型／严重度：成果 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：固定结果地图/表格/比较/可下载完整报告与适用服务发布
- 当前：实际raster/vector地图、点查、统计、bundle存在；没有完整ResultFacts报告、科研排版PDF/SVG/PNG模板或发布生命周期目录。OGC Processes执行协议不等于成果服务发布。
- 位置：`next/web/src/ResultArtifact.tsx`；`next/src/coastmas_next/package_download.py`；`next/src/coastmas_next/process_service.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)、[.review/evidence/runs/v3-audit-20260925/spatial/indicator-flow.json](../../.review/evidence/runs/v3-audit-20260925/spatial/indicator-flow.json)
- 根因：成果呈现/文件下载基础尚未延伸到报告和发布领域
- 影响：成果的完整业务交付或审查可靠性；阻塞下游：是
- 建议：基于冻结ResultFacts生成报告/图件，图例关闭不影响科学模板；发布单独授权并可撤销。
- 依赖：AUDIT-016；整改Wave 2

### AUDIT-033 · Copilot和AIAction审计链未进入当前系统

- 模块／类型／严重度：AI横切能力 · `MISSING_IMPLEMENTATION` · `P2_NORMAL`
- 要求：AI仅候选/草稿，嵌既有中心，工具数据受授权
- 当前：active next无AIAction或Copilot执行链；未发现本轮不必要LLM请求。旧规划/LLM代码不代表当前集成。
- 位置：`next/web/src/navigation.ts`；`next/src/coastmas_next/app.py`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/source-index.json](../../.review/evidence/runs/v3-audit-20260925/source-index.json)
- 根因：当前实现尚未绑定模块级Copilot和可审计动作
- 影响：AI横切能力的完整业务交付或审查可靠性；阻塞下游：否
- 建议：先做确定性接入/匹配；再以可核查草稿实现AI辅助，禁止自动决定阈值/权重/执行许可。
- 依赖：AUDIT-007, AUDIT-010；整改Wave 5

### AUDIT-034 · 标准支持阶段有差异，未达到统一任务使用与导出矩阵

- 模块／类型／严重度：标准适配 · `MISSING_IMPLEMENTATION` · `P1_MAJOR`
- 要求：识别/校验/语义/映射/使用/导出/损失逐档案可核对
- 当前：GeoTIFF/CSV/CSVW/GeoJSON/GPKG/Shapefile/CF可解析；STAC只是文档识别；CF仅一维时间及指定版本，Mesh/垂向与一般复杂标准链缺失。不能用上传成功代表计算或往返无损。
- 位置：`next/src/coastmas_next/profiles.py`；`next/src/coastmas_next/csvw.py`；`next/src/coastmas_next/temporal.py:31`
- 证据层级：SOURCE_CONFIRMED；[.review/evidence/runs/v3-audit-20260925/backend-junit.xml](../../.review/evidence/runs/v3-audit-20260925/backend-junit.xml)、[.review/evidence/runs/v3-audit-20260925/api.json](../../.review/evidence/runs/v3-audit-20260925/api.json)
- 根因：识别器/科学profile/任务接口不是同一能力边界
- 影响：标准适配的完整业务交付或审查可靠性；阻塞下游：是
- 建议：为每标准定义阶段能力和反例，复用已正确解析；有损或语义变化集中确认。
- 依赖：AUDIT-007, AUDIT-018；整改Wave 2

### AUDIT-035 · 部分目录仍显示旧标题和技术类型

- 模块／类型／严重度：界面职责与用语 · `UX` · `P2_NORMAL`
- 要求：V3领域名与产品层一致；普通使用不暴露工程合同
- 当前：菜单为研究任务/综合评价方法，目录标题仍任务管理/方法方案；数据输入继续“资料”、类型筛选展示geotiff/csvw等代码。模型/匹配缺完整专业操作，不能靠换名修复。
- 位置：`next/web/src/ManagedCatalog.tsx`；`next/web/src/AssetPicker.tsx`；`next/web/src/DomainDirectory.tsx`
- 证据层级：EXECUTED_AND_SOURCE；[.review/evidence/runs/v3-audit-20260925/supplement-browser.json](../../.review/evidence/runs/v3-audit-20260925/supplement-browser.json)、[.review/evidence/screenshots/v3-audit-20260925/coupler-task-preflight.png](../../.review/evidence/screenshots/v3-audit-20260925/coupler-task-preflight.png)
- 根因：共享目录历史label与V3术语尚未统一
- 影响：界面职责与用语的完整业务交付或审查可靠性；阻塞下游：否
- 建议：在业务职责接通后统一显示标签/类型中文；不改用户文件名、科学标识或审计原文。
- 依赖：AUDIT-006, AUDIT-007；整改Wave 3

## 9. 未做与停止点

本轮不宣称145条产品验收全部执行。逐条审计处置在机器清单与覆盖文件；未执行项明确NOT_RUN/工程BLOCKED。原data_quan正式业务模型/科学解释、恶意沙箱、全量性能、外部服务、跨全部算法标准与版本的数值验证未完成。已有工程夹具不得发布为科学结论。

完成诊断、统一清单、覆盖和整改路线后停止。没有自动进入修复或替换正式服务。

## 9. 复核入口与审计收尾

[诊断脚本及复现方式](../../scripts/audit_v3/README.md)。最后六条浏览器链在同一构建、58125隔离环境连续运行，6/6通过；携带可公开的合成夹具，原测试未删除/放宽断言。初轮第二浏览器遗留58013地址只涉及页面导航，API使用隔离baseURL；只读数据库核对审计项目在正式环境不存在，最终副本全部修正为58125。原错误记录保留。

本报告的覆盖是逐项处置，不意味着全部实测：未接通的业务、未运行专项和外部条件分别记录。整改路线已给出，本轮不进入实施。

审计隔离服务在作业全部结束后正常退出，私有空间及证据保留；[收尾检查](../../.review/evidence/runs/v3-audit-20260925/service-closeout.json)确认58013仍为HTTP200，没有向正式服务发送退出信号。
