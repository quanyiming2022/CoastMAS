在当前 CoastMAS V3 和
《CoastMAS-Codex-master-spec-20260925.md》基础上，
补充 Planning 业务具体化要求。


# CoastMAS V3 Planning 业务具体化与工程落地补充任务书

## 0. 执行优先级与 V3 一致性裁决

本补充以 **CoastMAS V3** 与《CoastMAS-Codex-master-spec-20260925.md》为唯一上位业务与工程基线。以下裁决优先于本文件中可能产生歧义的历史表述：

1. **V3 四类 Task 保持不变：**
   - Assessment
   - Simulation
   - Planning
   - Comparison

   不再退回“Assessment / Simulation / Planning 三类任务”，也不把跨方案比较重新实现成 Assessment 的特殊子模式。

2. **V3 Planning 可见八步保持不变：**

   ```text
   数据
   → 准备与对齐
   → 现状诊断
   → 规划目标
   → 约束与决策变量
   → 方案生成与优化
   → 方案评价与比较
   → 规划成果
   ```

3. “数据、准备与对齐、指标/状态认知可以共用”描述的是**底层能力复用**，不是要求 Assessment、Simulation、Planning 的前三个可见步骤采用相同名称、相同页面或同一张表单。

   Planning 的第 3 步始终是 **“现状诊断”**。其内部可以复用：

   ```text
   Indicator Engine
   + Assessment Result
   + Simulation Result
   + 原始状态数据
   + Diagnosis Recipe
                 ↓
           Diagnosis Engine
                 ↓
          DiagnosisVersion
   ```

   不得把 Planning 第 3 步重新改名为“指标与状态认知”。

4. **共用的是底层，不共用一张通用业务表单。** 四类任务可以共用：

   ```text
   Data
   Indicator
   Model
   Scene
   Scenario
   Workflow
   Runtime
   Result
   Provenance
   ```

   但 Assessment、Simulation、Planning、Comparison 必须保留各自业务步骤、状态和交互。

5. **V3 一级导航不因本补充改变。** 本补充只把 Planning / Comparison 的业务知识落成可执行对象、Recipe、Compiler、Workflow、API 与验收，不新增第二套“规划中心”，不把内部对象直接暴露为普通用户菜单。

6. **PlanningProblem 是冻结组合，不是目标/约束/决策变量的父级编辑容器。** 正确依赖方向为：

   ```text
   DiagnosisDraft/Version
   ObjectiveSetDraft/Version
   ConstraintSetDraft/Version
   DecisionSpecDraft/Version
   ScenarioVersion
   PlanningUnitSetVersion
              ↓
      PlanningProblemCompiler
              ↓
      PlanningProblemRevision
              ↓
        Solver Match / Run
   ```

   因此 Objective、Constraint、DecisionSpec 应允许先独立创建、自动保存草稿、发布不可变版本并被多个 PlanningProblem 复用。不得实现成“必须先创建 PlanningProblem，才能创建 Objective / Constraint / DecisionVariable”。

7. 如果当前数据库设计存在 `planning_objectives.problem_revision_id`、`planning_constraints.problem_revision_id` 等直接父子关系，实施时应调整为**集合版本 + 成员关系 + PlanningProblem 固定引用集合版本**。若内部为了查询保留 problem 反向关系，它只能是派生/关联关系，不能成为对象创建和版本化的前置条件。

8. **普通模式与专业模式必须分离。** 普通用户看到业务目标、现状问题、候选数据、必须避让、发展规模、允许改变什么、生成方案和方案比较；Objective expression、Constraint DSL、DecisionVariable domain、Solver params、Penalty、DAG、Convergence、Pareto、Resource estimates 仅在专业模式按需展开。

9. 后续实现若发现本文件与 V3 四类任务、V3 八步或主任务书的最新明确裁决发生冲突，优先采用：

   ```text
   用户最新明确要求
   > 本节 0 的一致性裁决
   > CoastMAS V3
   > CoastMAS-Codex-master-spec-20260925.md 中不冲突的工程细节
   > 本文件后续一般性描述
   ```

---

不是重新设计 Planning 架构，
V3 的 Planning 八步保持不变：

数据
→ 准备与对齐
→ 现状诊断
→ 规划目标
→ 约束与决策变量
→ 方案生成与优化
→ 方案评价与比较
→ 规划成果

本补充解决的是：
目前对象和Solver已经定义，但“规划业务知识如何真正落入系统”
仍需进一步明确。

==================================================
一、Planning 不是从空白目标表开始
==================================================

规划任务必须优先复用同一项目已有：

Assessment Result
Simulation Result
Indicator Result
Scenario
Data
Scene Object

建立正式引用关系，不下载再上传。

例如：

生态敏感性评价 Result
灾害风险评价 Result
2035城市扩张 Simulation Result
人口预测 Result
建设适宜性 Result

可以直接成为 PlanningInput。

所有引用固定：
task_id
run_id
result_id
resource_revision_id

不得引用“latest”形成不可复现规划。


==================================================
二、建立 Planning Diagnosis Recipe Library
==================================================

现状诊断不是LLM写文字，
而是已有指标/评价/模拟/空间数据经过确定性分析形成Planning Evidence。

系统内置第一批 Diagnosis Recipe：

1. spatial_conflict
   空间冲突诊断

2. development_pressure
   开发压力诊断

3. ecological_protection_gap
   生态保护缺口

4. disaster_exposure
   灾害暴露

5. carrying_capacity_pressure
   承载压力

6. infrastructure_service_gap
   基础设施服务缺口

7. low_efficiency_land
   低效建设用地

8. ecological_connectivity_gap
   生态连通性缺口

9. restoration_priority
   生态修复优先性

10. development_potential
    发展潜力

这些不是固定政策结论。
Recipe只定义算法结构和需要的输入。

具体阈值、法规、区域规则必须来自：
published rule
method profile
scenario
policy constraint
user-confirmed business rule

不能系统自行发明。

Diagnosis Recipe内部可以复用：

overlay
intersection
distance
zonal statistics
hotspot
classification
registered indicators
Assessment Result
Simulation Result
scene constraints

输出：

DiagnosisVersion
diagnostic raster/vector
diagnostic statistics
priority/conflict zones
evidence references
lineage

例如：

高生态敏感
+
高开发压力
→
空间冲突候选区

必须能够点选地图区域查看：
使用了哪些Result
哪些指标值
哪些规则
哪些阈值
哪个Run。


==================================================
三、Indicator 与 Objective 正式分开但建立映射
==================================================

必须明确：

Indicator描述状态。
Objective定义优化方向。

例如：

Indicator:
ecological_sensitivity

不能直接等同于Objective。

Objective可以是：

minimize occupation of high ecological sensitivity area

其计算可能依赖：
ecological_sensitivity indicator
+
planned land allocation

因此增加：

ObjectiveMetricDefinition

字段至少：

objective_code
name
category
metric_recipe_ref
required_indicator_refs
required_state_refs
direction
aggregation
unit
spatial_scope
time_scope
baseline_requirement
candidate_state_requirement

内置Objective Catalog至少包含：

经济：
maximize_land_economic_benefit
maximize_industrial_benefit
minimize_construction_cost
maximize_transport_accessibility

生态：
minimize_ecological_occupation
minimize_habitat_loss
maximize_ecological_connectivity
maximize_restoration_gain
maximize_carbon_gain

风险：
minimize_population_exposure
minimize_asset_exposure
minimize_high_risk_development
maximize_emergency_service_coverage

社会：
maximize_public_service_coverage
maximize_employment_accessibility
improve_spatial_equity
minimize_relocation_impact

空间结构：
maximize_compactness
minimize_fragmentation
maximize_connectivity
minimize_enclave
protect_ecological_corridor

普通用户选择业务目标，
系统自动绑定实际metric recipe。

普通用户不写目标函数代码。


==================================================
四、Objective支持三种明确模式
==================================================

A. single_objective

例如：
Minimize FloodRisk

B. weighted_multiobjective

只有用户明确选择该模式，
才要求权重：

Economic 0.3
Ecological 0.4
Risk 0.3

权重由用户/政策/已发布方案提供。
AI不得自行决定。

C. pareto_multiobjective

例如：

Max EconomicBenefit
Min EcologicalLoss
Min DisasterRisk

不要求预先WeightSet。

输出未支配候选。

禁止把所有多目标问题强制变成加权求和。


==================================================
五、建立真正的 Constraint Recipe Library
==================================================

约束库不是一列名称。

每个约束必须是可编译对象。

分类至少包括：

1. policy
2. natural
3. ecological
4. hazard
5. capacity
6. land_quota
7. distance
8. adjacency
9. connectivity
10. infrastructure
11. industrial_compatibility
12. budget
13. carbon
14. temporal

ConstraintRecipe字段至少：

constraint_code
name
hardness
required_inputs
expression_template
unit
scope_type
parameter_schema
effective_period
source_requirement
compiler_type
validation_profile

示例：

ecological_redline_exclusion

输入：
ecological_redline geometry

编译：
planning_unit intersect redline
→ forbidden=true

输出：
HardConstraintMask

不是让用户写：
x_i = 0


distance_to_road

输入：
road
planning units

参数：
max_distance

输出：
eligible/penalty

具体3km不能作为全局默认政策值；
只有明确任务/标准给出以后使用。


development_quota

输入：
planning unit areas

参数：
maximum development area

编译：
Σ area_i * x_i <= quota


connectivity

不能写成模糊的“尽量连续”。

必须选择真实实现：
graph connectivity
flow connectivity
adjacency penalty
patch compactness
或其他已发布profile。


==================================================
六、建立 Decision Variable Templates
==================================================

不同规划任务不能共用一个“变量类型”输入框。

至少建立以下模板：

A. LandUseAllocation

每规划单元未来用途：

x[g,c]

类别：
建设
农业
生态
湿地
产业
公共服务
...

支持：
one-hot
allowed transition
forbidden transition
locked current use


B. RestorationPlanning

变量：
repair/not repair
repair type
repair intensity


C. FacilityLocation

变量：
candidate site selected
facility capacity


D. DevelopmentIntensity

连续变量：
development intensity
investment
capacity
population
industry scale


E. LinearInfrastructure / Corridor

变量：
候选边/路径/网络选择

按实际实现能力开放。

普通用户看到：

“允许优化器改变什么？”

例如：

☑ 建设用地位置
☐ 原有生态用地
☑ 新增建设强度

而不是binary/integer变量表。


==================================================
七、Planning Template真正预装
==================================================

系统至少内置以下Planning Recipe Template：

建设用地优化
生态保护规划
生态修复优先区
产业空间布局
基础设施选址
防灾避险规划
湿地恢复规划
岸线利用规划
综合国土空间优化

模板不是一张说明卡。

每个模板必须定义：

推荐PlanningUnit
Diagnosis recipes
candidate Objective catalog
candidate Constraint recipes
DecisionVariable template
eligible Solver classes
default evaluation workflow
required inputs
optional inputs

例如：

生态修复优先区

Inputs:
ecological sensitivity
habitat quality
land use
connectivity
restorable land

Diagnosis:
ecological_connectivity_gap
restoration_priority

Objective:
maximize ecological gain

Constraint:
restorable_land
budget

Decision:
repair/not_repair

Solver:
ranking
MILP/other eligible solver

Evaluation:
ecological gain
connectivity improvement
cost
restored area


==================================================
八、Diagnosis → Objective之间建立业务建议关系
==================================================

允许系统根据Diagnosis提出Objective候选：

例如：

Diagnosis：
高风险人口暴露

建议：
minimize_population_exposure

Diagnosis：
生态廊道断裂

建议：
maximize_ecological_connectivity

Diagnosis：
低效建设用地

建议：
improve_land_use_efficiency

但这只是推荐。

用户明确选择后才进入ObjectiveSet。

AI可以解释推荐原因，
不能自动改变ObjectiveSet。


==================================================
九、Objective → Constraint / Decision同样可以推荐
==================================================

例如：

用户选择：

minimize_population_exposure

系统可以提示：

可能需要：
flood risk
population
development decision variables

但不能自动生成政策约束。

用户选择：

port location planning

可以推荐：

DecisionVariable:
facility_selection

可能Constraint：
depth/draft条件
road accessibility
ecological protection
storm surge risk

仍需数据和业务规则确认。


==================================================
十、PlanningProblemCompiler
==================================================

### 10.1 对象依赖方向强制裁决

PlanningProblem 不是 Objective / Constraint / DecisionVariable 的父级编辑容器，而是对一组**已经独立版本化的科学与业务对象进行冻结组合**。

必须实现：

```text
ObjectiveSetDraft
→ ObjectiveSetVersion

ConstraintSetDraft
→ ConstraintSetVersion

DecisionSpecDraft
→ DecisionSpecVersion

DiagnosisDraft/Run
→ DiagnosisVersion

ScenarioDraft
→ ScenarioVersion

PlanningUnitSet
→ PlanningUnitSetVersion
```

然后由：

```text
PlanningUnitSetVersion
+ BaselineState / ScenarioVersion
+ DiagnosisVersion
+ ObjectiveSetVersion
+ ConstraintSetVersion
+ DecisionSpecVersion
+ EvaluationWorkflowVersion
              ↓
      PlanningProblemCompiler
              ↓
      PlanningProblemRevision
```

数据库至少要满足：

```text
objective_sets / objective_set_revisions / objective_items
constraint_sets / constraint_set_revisions / constraint_items
decision_specs / decision_spec_revisions / decision_variables
diagnosis_revisions
planning_problem_revisions
```

`planning_problem_revisions` 固定引用：

```text
planning_unit_set_revision_id
baseline_state_ref
scenario_revision_id
diagnosis_revision_id
objective_set_revision_id
constraint_set_revision_id
decision_spec_revision_id
evaluation_workflow_revision_id
```

不得要求 ObjectiveItem、ConstraintItem、DecisionVariable 在创建时已经知道 `planning_problem_revision_id`。

若为了高效查询保存 Problem ↔ Set/Item 反向关系，必须从冻结引用派生或通过关联表维护，不能改变上述业务依赖方向。

这样必须支持：

- 一个 ObjectiveSet 被多个 PlanningProblem 复用；
- 一个 ConstraintSet 在不同 Scenario 中按版本复用；
- 修改草稿不会改变已冻结 PlanningProblem；
- 新发布 ObjectiveSet/ConstraintSet 不自动升级历史 Problem/Run；
- 用户选择新版本后创建新的 PlanningProblemRevision；
- 历史 Run 仍完整引用旧版本并可复现。

### 10.2 PlanningProblem 编译

PlanningProblem不是用户手写。

系统由：

PlanningUnitSet
+
BaselineState
+
Scenario
+
DiagnosisVersion
+
ObjectiveSetVersion
+
ConstraintSetVersion
+
DecisionSpecVersion
+
EvaluationWorkflowVersion

编译为：

PlanningProblemRevision

Compiler必须检查：

数据完整性
目标是否有真实metric
变量是否可以产生目标变化
约束是否可表达
单位
时空域
索引一致性
变量数量
约束数量
solver compatibility
resource estimate

不能出现：

目标“提高生态连通性”
但DecisionVariable完全不会改变任何生态对象。

此情况必须提示：
“当前决策变量无法影响该目标。”


==================================================
十一、Solver Registry保持独立
==================================================

Solver只解决已经定义好的PlanningProblem。

至少分类：

rule_based
ranking
LP
ILP
MILP
CP-SAT
Goal Programming
Network Optimization
GA
NSGA-II
MOEA/D
PSO
Simulated Annealing
Ant Colony
QUBO
Quantum/Hybrid Adapter

Solver Matcher依据：

variable domain
objective type
constraint type
problem scale
resource
license
multiobjective support
checkpoint capability

决定：

eligible
ineligible
scale_risk

不能把Solver名称做成一个随便可选的下拉菜单。


==================================================
十二、Plan Candidate必须是完整状态方案
==================================================

一个Run可以输出多个：

PlanCandidate

每个Candidate至少具有：

candidate_id
spatial allocation/state
objective vector
solver diagnostics
independent feasibility report
constraint residuals
scenario ref
problem ref
run ref

Candidate不得覆盖baseline。

不能因为Solver返回第一名，
就称“最终规划”。


==================================================
十三、规划再评价必须复用Assessment体系
==================================================

这是必须实现的核心闭环。

PlanCandidate
→
Candidate State
→
Indicator Engine
→
Assessment / Evaluation Workflow
→
PlanEvaluation

必须重新计算受方案影响的：

建设面积
生态占用
湿地变化
生态连通性
风险暴露
人口覆盖
经济收益
建设成本
服务覆盖
空间破碎度
等已注册指标。

不得只显示Solver内部objective value。

必须能回答：

相对Baseline：

减少多少高风险面积？
减少多少人口暴露？
增加多少生态保护面积？
改变多少湿地？
增加多少建设成本？
连通性变化多少？

按照已有ImpactPropagation规则，
未受影响节点可以复用；
受影响节点必须真实重新计算。


==================================================
十四、Comparison必须形成独立Task
==================================================

规划内部的Step7可以比较本次Candidate。

跨任务/跨Scenario/跨Run比较则形成：

Comparison Task

例如：

方案A
方案B
方案C
Baseline

Comparison流程保持：

选择方案
→统一比较口径
→评价指标
→统计分析
→空间差异
→权衡分析
→敏感性分析
→比较成果

不能把Comparison缩成Plan表格上的三列数字。


==================================================
十五、三维场景作为Planning输入/约束来源
==================================================

Scene Object可以映射为：

PlanningUnit
DecisionObject
ConstraintObject
EvaluationObject

例如：

建筑 → exposure / relocation cost
道路 → accessibility
地块 → planning unit
湿地 → ecological constraint
岸线 → setback/distance
堤防 → flood defense
港口 → facility/object

但Scene Object本身不自动形成法律Constraint。

必须经过：

SceneObject
→
ConstraintRecipe
→
CompiledConstraint

三维展示精度与分析几何精度分开。


==================================================
十六、Coupler升级必须实际覆盖Planning
==================================================

Coupler的匹配输入扩展为：

Data
Indicator
Model
Scenario
Objective
Constraint
DecisionVariable
Solver
Scene

Planning Matcher必须能够回答：

数据够不够？
指标够不够？
目标能否计算？
约束能否表达？
决策变量是否匹配？
问题规模多大？
哪些Solver可以运行？
需要哪些Adapter？

输出真实Binding/Coupling/WorkflowPlan。


==================================================
十七、知识关系扩展
==================================================

统一图关系至少允许：

Object
Data
Indicator
Algorithm
Model
Scenario
Objective
Constraint
DecisionVariable
Solver
Workflow
Result
Plan
Service

但知识图只是关系模型，
不能直接当执行DAG。

执行仍编译成固定WorkflowVersion。


==================================================
十八、普通模式与专业模式
==================================================

普通规划用户只看到：

研究目标
现状问题
候选数据
规划目标
必须避让
发展规模
允许改变什么
生成方案
方案比较

专业模式才展开：

Objective expression
Constraint DSL
DecisionVariable domain
Solver params
Penalty
DAG
Convergence
Pareto
Resource estimates

不要把专业模式字段直接放到普通模式。


==================================================
十九、增加端到端验收
==================================================

PLAN-E2E-01 建设用地优化

输入：
landuse
road
ecological sensitivity Result
flood risk Result

流程：
Diagnosis
→ Objectives
→ Constraints
→ LandUseDecision
→ Solver
→ Candidate A/B/C
→ Re-evaluation
→ Comparison

要求：
真实空间方案、独立约束检查、真实指标变化。


PLAN-E2E-02 生态修复

输入：
landuse
habitat
connectivity
budget

输出：
restoration candidate map
restoration plan
cost
ecological gain
connectivity improvement


PLAN-E2E-03 防灾设施选址

输入：
population
risk
road/accessibility
candidate sites

输出：
facility selection
coverage
cost
residual uncovered risk


PLAN-E2E-04 多目标

Economic max
Ecological loss min
Risk min

使用NSGA-II或其他实际多目标solver。

要求：
真实non-dominated candidates，
不得自动选择“最佳”。


PLAN-E2E-05 Assessment→Planning→Assessment

固定Assessment Result
→ Planning
→ Candidate
→ Assessment re-evaluation

必须证明：
规划前后的评价差异来自Candidate State，
不是复用原Assessment结果。


==================================================
二十、与当前任务书的关系
==================================================

以上直接补充到：

W12 Coupler
W14 Planning
W09 Comparison
W15 Scene
W17 Result/Report

不改变V3菜单、
不改变四类Task定义、
不建立另一套规划系统。

当前正确的PlanningProblem、Solver、
Constraint、DecisionVariable、PlanCandidate、
PlanEvaluation、Run、Lineage设计继续保留。

目标是把原来详细的规划业务设计
真正变成系统可执行的对象、recipe、compiler和workflow，
而不是再增加说明文字和页面入口。

==================================================
二十一、给 Codex 的最终执行约束
==================================================

按本文件直接实施，不再另写一份 Planning 总体设计。

实施时：

1. 先读取当前 Planning / Comparison / Coupler / Solver / Scene / Run 的真实代码与迁移，复用已正确实现；不要只根据旧页面推断后台不存在能力。
2. 将本文件要求映射到现有 W09、W12、W14、W15、W17 及相关数据库/API/前端测试；必要时修改当前 schema 和接口，不承担旧私有结构兼容义务。
3. 所有 Built-in Recipe / Objective / Constraint / Decision Template 必须区分 `可执行`、`未实现`、`研究中`。普通用户只看到真实可运行或明确可配置的能力，不得把名称注册当完成。
4. 现状诊断、目标、约束、决策变量、求解、再评价、Comparison 必须有真实对象、固定版本、Run/Result、血缘和恢复；不能只保存前端表单状态。
5. AI 只能推荐、解释、生成草稿或调用真实工具；Diagnosis、Objective metric、Constraint compilation、Solver result、PlanEvaluation 的数值真源必须来自确定性算法/已批准模型和固定输入。
6. 普通模式最少填写；系统已有数据、指标、上游结果、模板和规则可自动确定的内容不重复要求用户填写。只有科学歧义、政策/业务选择、会改变解释的转换或确需人工价值判断时才提示用户。
7. 规划候选不是正式规划；`Calculated / Reviewed / Published` 分离。算法完成不得自动变成业务批准或服务发布。
8. 最终提交同一构建的真实证据：UI、API、数据库迁移、算法/求解、Run、候选、再评价、Comparison、报告及 PLAN-E2E-01～05。未运行项标 `NOT_RUN`，科学资料缺失项标 `BLOCKED`，不得用截图或 HTTP 200 冒充数值验收。

本文件最终目的不是增加更多配置页面，而是把 V3 中：

```text
Assessment
→ Diagnosis
→ Planning
→ PlanCandidate
→ Assessment Re-evaluation
→ Comparison
→ Result / Service
```

真正实现成可执行、可追溯、可复现、可扩展的海岸带分析与规划闭环。

