对当前《CoastMAS-Codex-master-spec-20260925.md》增加以下
“强制工程纠偏要求”。

这不是新总体方案，也不重做现有架构。
与原任务书冲突时，以本补充要求和用户最新要求为准。
目标是让算法真正可执行、Coupler可诊断、AI有边界、
规划可控、界面专业，同时保留原任务书的版本、权限、
可重复性和科学校验。

一、核心算法采用“系统内置可执行算子”，不是只注册名称

建立 BuiltinOperatorRegistry。

以下高频基础能力必须随系统安装、无需额外插件即可执行：

指标类：
NDVI、EVI、SAVI、NDWI、MNDWI、NDBI、
坡度、距离、缓冲、面积比例、密度、
土地利用强度、土地利用动态度、
城市扩张速度/强度等首批核心指标。

评分/标准化：
Min-Max、正向/负向、固定区间、
类别评分、Z-score等已明确方法。

赋权：
AHP、Entropy、CRITIC、
变异系数、标准差、手工/等权等。

评价：
WLC、TOPSIS等已确定并测试的方法。

分级：
Jenks/Fisher-Jenks、Quantile、
Equal Interval、Standard Deviation、
Geometric Interval、自定义阈值。

这些方法必须：
- 有真实代码实现；
- 有版本；
- 有固定输入输出契约；
- 有数值测试；
- 有异常测试；
- 普通用户开箱即用。

“Built-in”不是散落硬编码。
仍统一经过Algorithm/Operator接口、版本和测试体系。

普通用户不能看到“已注册但无执行器”的算法。
未实现能力只能出现在维护/研发状态，不能作为可选生产功能。

二、严格区分 WeightEstimator / DirectEvaluator / DimensionalityReducer

API、数据库和前端类型必须分开。

WeightEstimator：
输出合法WeightSet，可供WLC等使用。

DirectEvaluator：
直接输出score，不再强制转换成WeightSet。

DimensionalityReducer：
输出components/loadings/transformed features，
不自动具有评价含义。

PCA默认进入DimensionalityReducer/DirectEvaluator路径。
只有具名、已发布、具有明确文献/规则的
“PCA-derived weighting profile”才允许输出WeightSet。

Projection Pursuit同样根据具体实现分别注册为：
WeightEstimator或DirectEvaluator。

禁止：
PCA载荷、
RF重要度、
回归系数、
任意PP方向
未经定义直接归一化成WeightSet。

三、第三方模型采用 Manifest-first，不采用“盲猜黑箱”

所有正式发布的第三方模型版本必须具有ModelContract。

但不要要求普通用户手工写JSON。

支持三种路径：

A. CoastMAS SDK模型
由SDK生成contract模板并进行schema校验。

B. 旧Python/R/CLI模型
系统静态分析和AI只生成contract草稿：
输入端口、输出端口、参数、环境、时空要求等。
模型维护者确认后才能进入验证。

C. Docker/REST/HPC/BMI
通过对应Adapter生成contract并进行连通/IO验证。

未经确认的自动推断只能是draft，
不能成为published contract。

不能因为“源码解析成功”就声明模型解耦完成。

四、建立 Matcher Diagnostic Inspector

Coupler匹配失败或需要适配时，
普通用户不能只看到“无法匹配”。

增加统一诊断对象：

MatcherIssue:
- requirement
- candidate
- gate_type
- actual
- required
- severity
- adaptable
- suggested_adapter
- affected_node
- evidence

界面按三类显示：

1. 已满足
例如：
“人口栅格已满足模型输入要求。”

2. 可自动适配
例如：
“分辨率10m → 30m，需要重采样。”
“单位万人 → 人，可以精确转换。”
“CRS不同，可以重投影到目标网格。”

提供：
[采用推荐方案]
[查看处理计划]

3. 硬阻断
例如：
“源数据缺少可靠坐标系。”
“当前变量为人口总量，模型需要人口密度，
且尚未确定面积/空间分配方法。”
“当前用户无权使用该模型版本。”

硬门禁与可适配差异不能混为同一种失败。

专家模式可展开完整Coupler证据：
hard gates、候选评分、adapter path、loss、cost和来源。

五、AI严格作为Copilot，不直接产生科学数值结果

LLM允许：

- 年鉴/CSV表头理解；
- 字段和单位候选；
- 研究目标解析；
- 指标/模型搜索与推荐；
- ModelContract草稿辅助；
- Coupler缺口解释；
- Adapter路径建议；
- 代码和测试草稿；
- 规划目标/约束候选；
- 报告文字草稿。

LLM禁止直接：

- 生成最终权重；
- 计算矩阵结果；
- 修改像元值；
- 做空间插值结果；
- 产生优化解；
- 决定规划价值权重；
- 伪造缺失统计值；
- 修改确定性算法结果。

所有最终数字必须来自：
Python/R/C++/GDAL/PROJ/GEOS/
SciPy/scikit-learn/求解器/已批准模型等确定性工具。

AI只负责“理解、建议、编排、解释”。

六、AIAction前端提供可审计记录，但不得泄露秘密

不要直接展示完整系统Prompt或秘密信息。

AIAction至少记录并可查看：

- action type
- provider/model
- prompt_template_id/version/hash
- 使用的数据版本
- 脱敏后的输入摘要
- 结构化AI输出
- 实际调用的工具及参数摘要
- 工具真实返回引用
- 用户是否接受/修改/拒绝
- 最终产生的配置diff
- token/cost真实回执
- 时间和操作者

对于项目自定义Prompt，可按权限查看正文。
系统级秘密Prompt、API key、受限数据全文不得暴露。

AI建议必须标为“建议”，
真正应用前产生结构化diff并由用户确认或按已有自动规则执行。

七、规划求解前建立 Resource & Scale Preflight

不要用一个固定“超过几千变量就禁止”的阈值。

每个SolverProfile维护自己的能力和资源策略。

运行前计算：

- planning unit数量
- decision variable数量
- integer/binary/continuous数量
- constraint数量
- non-zero矩阵规模
- adjacency/network规模
- 预计内存
- 预计CPU/GPU
- time limit
- solver license/remote cost
- checkpoint/warm-start能力

输出：

可直接运行
/
高成本但允许
/
建议缩减
/
当前资源不支持

高成本时给真实替代路线，例如：

- candidate screening
- zonal aggregation
- hierarchical optimization
- decomposition
- coarse-to-fine
- sampling
- rule-based prefilter
- surrogate model
- heuristic approximation

这些近似路线必须记录approximation profile，
并回到原全域进行约束和结果验证。

不得仅因用户点击确认就允许明显会OOM的任务硬跑。

八、方案再评价采用“依赖影响域驱动”，不是简单全图重算

建立 ImpactPropagation / IncrementalEvaluation 机制。

每个算法节点声明 locality：

LOCAL
WINDOWED(halo)
GLOBAL_APPLY
GLOBAL_FIT
NETWORK_GLOBAL
STATEFUL_SIMULATION

PlanCandidate产生ChangeSet：
changed cells/features
changed attributes
changed classes
changed constraints
changed scenario values

DAG根据依赖传播计算AffectedSet。

可局部重算：
- 分类面积
- 局部土地利用指标
- 部分距离/缓冲
- 邻域统计（带正确halo）
- 局部暴露统计
等。

必须重算或重新fit的例子：
- PCA重新拟合
- Entropy/CRITIC重新拟合
- 全局min/max评分
- 全局连通性
- 网络路径
- 水动力/扩散模型
- 依赖全域边界条件的模型
- 全局优化
等。

未变化且依赖未受影响的节点直接引用旧Run固定结果。

禁止“变化掩码=所有算法局部重算”的错误优化。

九、全面禁止Modal Hell

复杂编辑不使用嵌套Modal。

默认交互：

中央Workspace
+
右侧Inspector
+
底部可调Dock

Modal仅用于：
短确认、危险操作、少量字段快速创建。

以下不得默认用全屏Modal：
指标配置
AHP矩阵
模型契约
规划目标/约束
大型表格
工作流
Coupler诊断

打开和关闭编辑器不能破坏地图、图层、当前任务和草稿状态。

十、Draft / Publish / Approve严格分离

所有复杂配置：

Draft：
实时服务器保存，可不完整。

Publish：
形成不可变版本，执行完整业务校验。

Approve：
有权限用户将固定版本批准为特定使用范围。

包括：
指标定义
方法
模型
Scenario
Constraint
Objective
Workflow
Solver Profile等。

刷新、崩溃、会话失效后，
已确认写入服务器的Draft必须能恢复。

大矩阵可保存到对象存储/专用表，
不能依赖前端内存。

十一、CRS和空间对齐采用“自动计划 + 有影响才确认”

准备与对齐步骤必须显示：

数据
CRS
分辨率
网格
范围
时期
拟处理
影响
状态

以下可自动规划并在已有规则允许时自动执行：

- 明确源CRS到明确目标CRS的标准重投影；
- 已认可连续量重采样；
- 已认可分类数据最近邻；
- 精确单位换算；
- 明确GridSpec对齐。

以下必须人工处理/确认：

- 源CRS未知或冲突；
- 垂向基准未知；
- 分类合并；
- 总量→密度/空间分配；
- 降尺度；
- 会改变科学含义的插值；
- 有明显信息损失的转换。

不要每次CRS不同都弹确认。
也不能后台静默执行会改变科学解释的适配。

地图显示重投影与正式分析网格重投影仍然分开。

十二、增加专项验收

新增以下验收：

ENG-ALG-01
内置NDVI/AHP/Entropy/CRITIC/WLC/Jenks
在无任何第三方插件时可以真实执行。

ENG-ALG-02
删除/禁用扩展插件后，
系统内置核心算法仍可运行。

ENG-TYPE-01
PCA DirectEvaluator结果不能传入WLC的weight_set参数。

ENG-TYPE-02
具名PCA-derived weighting profile经发布后才可产生WeightSet。

ENG-MODEL-01
无ModelContract第三方包只能生成draft，
不能直接发布运行。

ENG-MATCH-01
10m→30m合法适配显示“可处理”，不是硬失败。

ENG-MATCH-02
未知CRS显示硬阻断并定位具体数据。

ENG-AI-01
AI推荐指标后不点击应用，
任务配置与结果完全不变。

ENG-AI-02
AI生成错误数字不能进入ResultFacts；
最终结果只取工具返回。

ENG-PLAN-01
大规模问题运行前产生变量/约束/内存估计。

ENG-PLAN-02
超资源问题不能直接启动worker导致OOM；
需得到缩减/替代路线。

ENG-INCR-01
局部土地变化只重算受影响LOCAL/WINDOWED节点。

ENG-INCR-02
改变会影响Entropy/PCA fit的数据后，
GLOBAL_FIT节点必须重新计算，不能复用旧模型。

ENG-CRS-01
两个CRS不同但合法可转换的数据，
生成明确对齐计划并正确输出目标网格。

ENG-CRS-02
未知CRS不能通过默认EPSG:4326“修复”。

ENG-DRAFT-01
AHP矩阵填写一半后刷新浏览器，草稿可恢复。

ENG-UI-01
指标/AHP/Coupler/规划复杂编辑均无嵌套Modal，
地图上下文保持。

十三、实施方式

这些要求直接并入现有W任务：

W07：
内置可执行指标/算法注册。

W08：
WeightEstimator/DirectEvaluator/Reducer类型隔离。

W10：
Manifest-first ModelContract及模型接入。

W12：
Matcher Diagnostic Inspector及合法适配路径。

W14：
规模预检、Solver预算、ChangeSet再评价。

W16：
AI Copilot边界及AIAction审计。

W03/W05：
Workspace、Dock、对齐交互、CRS计划。

W11：
Draft恢复、运行资源与增量DAG基础。

不要新建另一份架构体系，
直接修改现有代码、契约、测试和验收矩阵。

最终报告必须说明：
哪些能力原来已有并复用；
哪些本次新增；
哪些算法真实可执行；
哪些仍是扩展/研究状态；
哪些测试PASS/FAIL/BLOCKED/NOT_RUN。

不得以“页面增加入口”“契约已定义”“算法已注册”
替代真实执行和数值验证。