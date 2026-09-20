# 海岸带可持续综合管理智能模型集成与场景化分析系统  
## Codex 单任务研发总任务书

**任务性质：科研项目完整软件研发任务**

**执行模式：单任务、全量实现、一次交付**

本任务不是架构咨询、技术预研或阶段设计任务。

你必须在本次任务中完成：

- 需求落实；
- 系统架构；
- 数据库；
- 后端；
- 前端；
- 模型运行框架；
- 模型智能拆解与集成器；
- 场景化模型接口器；
- 海岸带科研示范模型；
- 知识图谱；
- 大语言模型智能代理；
- 模型工作流；
- 场景适配；
- 动态综合评价；
- 多主体协同示范；
- 样例数据；
- 自动化测试；
- E2E测试；
- Docker部署；
- API文档；
- 用户手册；
- 技术文档；
- 科研验证实验；
- 最终验收报告。

允许你在内部把工程拆成若干 implementation tasks，但：

**禁止要求用户分阶段确认。**

**禁止完成某一阶段后停止。**

**禁止仅输出设计文档而不实现。**

**禁止把后续工作留成 TODO。**

**必须在当前任务中持续完成整个研发闭环，直到满足本文 Definition of Done。**

---

# 1. 项目名称

暂定：

**CoastMAS — 海岸带可持续综合管理智能模型集成与场景化分析系统**

英文：

**Coastal Management Analysis Studio**

项目名称必须配置化，后续可以修改品牌名称，不得写死在业务核心代码中。

建议仓库名：

```text
coastmas
```

---

# 2. 项目定位

本项目是一个需要独立交付给科研项目委托方的完整软件科研成果。

系统必须：

```text
独立代码仓库
+
独立数据库
+
独立部署
+
独立用户体系
+
独立模型体系
+
独立运行
+
独立验收
```

不得依赖现有 GeoAI Platform 才能运行。

同时，系统内部的通用能力必须保持标准化，使未来能够通过 API / Adapter 与 GeoAI Platform 集成。

因此架构必须遵循：

```text
通用模型编排核心
        +
海岸带领域包
        +
独立海岸带应用系统
        +
GeoAI Integration Adapter
```

严禁：

```text
直接修改现有 GeoAI Platform 核心代码
把 GeoAI 源码复制进本项目
使 CoastMAS 必须依赖 GeoAI 才能运行
把海岸带专业概念写死在通用模型编排核心
```

---

# 3. 总体研究目标

围绕海岸带可持续综合管理，完成以下三类研究目标的软件化实现。

## 3.1 模型智能拆解与集成

针对：

- 统计评价模型；
- 过程机理模型；
- 机器学习模型；
- GIS / Raster空间分析模型；
- 外部专业数值模型；

建立统一模型描述、组件化表达、输入输出依赖、适用条件和约束体系。

实现：

```text
管理需求
↓
任务理解
↓
任务拆解
↓
数据需求识别
↓
模型检索
↓
模型筛选
↓
模型组合
↓
变量级连接
↓
科学约束校验
↓
可执行工作流
↓
任务调度
↓
结果追溯
```

形成：

# 模型智能拆解与集成器

---

## 3.2 场景化模型适配

围绕：

```text
管理目标
+
地理区域
+
地理实体
+
时间范围
+
情景条件
+
实际数据
+
模型参数
+
边界条件
```

建立：

```text
场景
→ 地理实体
→ 数据
→ 模型变量
→ 参数
→ 模型运行
→ 结果
→ 地理实体
```

的完整映射机制。

形成：

# 场景化模型接口器

---

## 3.3 可持续状态动态综合评价

建立通用的指标评价引擎，对：

- 资源利用；
- 空间潜力；
- 系统脆弱性；
- 系统稳定性；
- 发展韧性；
- 可接受性；

进行可配置、多时期、空间化综合评价。

注意：

不得把固定指标体系写死为唯一科学定义。

必须设计为：

```text
Indicator Framework
+
Indicator Definition
+
Normalization
+
Weighting
+
Aggregation
+
Classification
+
Temporal Comparison
+
Spatial Statistics
```

内置一套研究示范指标配置即可。

---

# 4. 最终系统总体架构

实现以下逻辑架构：

```text
┌──────────────────────────────────────────────┐
│               CoastMAS Web UI                │
├──────────────────────────────────────────────┤
│                                              │
│ Dashboard                                    │
│ Model Center                                 │
│ Knowledge Graph                              │
│ Smart Planner                                │
│ Workflow Studio                              │
│ Scene Workspace                              │
│ Data Catalog                                 │
│ Assessment Center                            │
│ Run Center                                   │
│ Result Center                                │
│ Research Evaluation                          │
│ System Administration                        │
│                                              │
├──────────────────────────────────────────────┤
│                 API Gateway                  │
├──────────────────────────────────────────────┤
│                                              │
│ Model Orchestration Core                     │
│ Scene Binding Engine                         │
│ Workflow Engine                              │
│ Validation Engine                            │
│ LLM Agent                                    │
│ Knowledge Graph Service                      │
│ Assessment Engine                            │
│ Provenance Engine                            │
│                                              │
├──────────────────────────────────────────────┤
│              Execution Layer                 │
│                                              │
│ Python Adapter                               │
│ CLI Adapter                                  │
│ Docker Adapter                               │
│ HTTP Adapter                                 │
│ GIS/Raster Adapter                           │
│ ML Adapter                                   │
│ External Scientific Model Adapter            │
│                                              │
├──────────────────────────────────────────────┤
│               Data Layer                     │
│                                              │
│ PostgreSQL + PostGIS                         │
│ Object Storage                               │
│ Redis / Job Queue                            │
│ Knowledge Graph                              │
│                                              │
└──────────────────────────────────────────────┘
```

---

# 5. 推荐技术栈

除非当前运行环境存在明显兼容问题，否则优先采用：

## Backend

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
GeoAlchemy2
Rasterio
GeoPandas
Shapely
PyProj
Pint
NumPy
Pandas
SciPy
scikit-learn
NetworkX
```

知识图谱优先：

```text
Neo4j
```

如果 Neo4j 环境确实无法稳定部署，可以使用 PostgreSQL 图关系表 + NetworkX 实现同等业务能力，但必须保留独立 KnowledgeGraphService 接口。

---

## Database

```text
PostgreSQL
PostGIS
```

---

## Queue

```text
Redis
Celery / Dramatiq
```

选择一种稳定实现。

必须支持：

```text
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

---

## Object Storage

优先：

```text
MinIO
```

存放：

- GeoTIFF；
- NetCDF；
- 模型中间结果；
- 上传文件；
- 模型包；
- 工作流输出；
- 实验结果。

---

## Frontend

推荐：

```text
React
Next.js
TypeScript
```

地图：

```text
MapLibre GL
```

图表：

```text
ECharts
```

工作流：

```text
React Flow
```

---

## Deployment

必须提供：

```text
Dockerfile
docker-compose.yml
.env.example
```

最终必须达到：

```bash
docker compose up -d
```

可以启动完整系统。

---

# 6. 核心设计原则

所有模块遵循以下原则。

## 6.1 科学硬约束优先

模型选择流程：

```text
Hard Constraint Validation
        ↓
Candidate Models
        ↓
Soft Ranking
```

禁止：

```text
用一个综合得分抵消单位错误
用模型推荐概率抵消数据缺失
用LLM判断代替CRS检查
用LLM猜测缺失参数
```

---

# 7. 核心标准对象

必须实现以下领域对象。

---

## 7.1 ModelSpec

所有模型必须使用统一模型契约。

至少包含：

```text
id
name
display_name
version
model_type
description

capabilities
scientific_domain

inputs
outputs
parameters

spatial_scale
temporal_scale

supported_geometry
supported_crs

runtime_type
runtime_config

constraints

validation_status
validation_metrics

references

owner
license

created_at
updated_at
```

其中：

```text
model_type
```

至少支持：

```text
STATISTICAL
PROCESS
MACHINE_LEARNING
RASTER
GIS
HYBRID
EXTERNAL
```

---

## 7.2 VariableSpec

每个模型输入输出必须声明：

```text
name
standard_name
description

data_type

unit
dimension

semantic_type

spatial_support
temporal_support

aggregation_type

nodata_policy

required
```

---

## 7.3 DataAssetSpec

至少：

```text
id
name
type

uri
format

crs
vertical_datum

spatial_extent

time_start
time_end
time_resolution

variables

quality

source
license

version
checksum
```

---

## 7.4 SceneSpec

必须用于场景化接口。

至少：

```text
id
name

management_goal

study_area

entity_types

time_range

scenario_conditions

constraints

required_outputs

data_policy

quality_requirements
```

---

## 7.5 WorkflowSpec

至少：

```text
id
name
version

scene_type

nodes
edges

input_bindings

parameter_bindings

constraints

validation_rules

execution_policy

output_definition
```

---

## 7.6 BindingPlan

表示：

```text
DataAsset
→
Transformation
→
Model Variable
```

记录：

```text
source
target
semantic_mapping
unit_conversion
crs_transform
resampling
temporal_transform
quality_check
status
```

---

## 7.7 ExecutionJob

至少：

```text
id
workflow_id
scene_id

status

submitted_by

started_at
finished_at

progress

current_node

error

logs
```

---

## 7.8 RunManifest

必须冻结：

```text
SceneSpec version
WorkflowSpec version
ModelSpec versions
DataAsset versions
parameters
software version
container image
timestamp
random_seed
```

保证科研可复现。

---

## 7.9 ResultManifest

至少：

```text
id
job_id

result_type
storage_uri

entity_binding

spatial_extent
time_range

unit

quality_status

provenance

created_at
```

---

# 8. 模型智能拆解与集成器

这是核心科研成果一。

必须是一个完整的软件模块，不是一个聊天窗口。

---

## 8.1 模型注册中心

实现：

```text
新增模型
编辑模型
版本管理
启用/禁用
搜索
过滤
导入
导出
复制
验证
删除保护
```

支持：

```text
ModelSpec JSON
ModelSpec YAML
```

---

# 9. 模型拆解能力

模型拆解不得简单解释成：

> 让LLM随意拆代码。

必须实现两种拆解模式。

## 9.1 White-box Model

允许解析：

```text
Python Function
Pipeline
CLI arguments
Declared Components
```

形成：

```text
preprocess
compute
postprocess
validate
```

组件。

---

## 9.2 Black-box Model

对于：

- 外部exe；
- Docker；
- 水动力程序；
- 商业软件；
- 不允许修改的软件；

作为：

```text
Atomic Model Component
```

整体封装。

禁止大模型擅自修改其内部科学逻辑。

---

# 10. 模型知识图谱

必须建立：

```text
Objective
Task
Model
Variable
DataType
EntityType
SceneType
Constraint
```

等节点。

关系至少：

```text
REQUIRES
PRODUCES
SUPPORTS
DEPENDS_ON
MAPS_TO
VALID_FOR
INCOMPATIBLE_WITH
DERIVED_FROM
CAN_FOLLOW
```

前端必须提供：

# Knowledge Graph Explorer

能够交互查看：

```text
模型
→ 输入变量
→ 数据
→ 输出变量
→ 下游模型
```

---

# 11. 管理目标智能理解

提供自然语言输入：

例如：

```text
分析某海岸段在0.5米海平面上升情景下，
土地利用和人口受到的影响，
并按照管理单元统计风险。
```

LLM必须输出结构化：

```text
ManagementGoal
TaskGraph
RequiredData
RequiredCapabilities
CandidateWorkflow
MissingConditions
```

必须通过 Pydantic / JSON Schema 校验。

不得直接执行自由文本生成结果。

---

# 12. LLM智能代理

实现：

```text
LLMProvider
```

接口。

支持至少：

```text
OpenAI-compatible API
```

同时必须提供：

```text
Deterministic Fallback Planner
```

这样即使没有 LLM API Key：

系统仍然可以运行样例工作流。

LLM只能：

```text
理解需求
拆解任务
推荐已注册模型
说明推荐依据
生成结构化Workflow候选
```

LLM禁止：

```text
凭空创造不存在的模型
绕过模型注册中心
绕过科学校验
直接修改模型参数越界值
自动认为缺失数据存在
```

---

# 13. 模型检索与匹配

必须实现两级筛选。

## 13.1 Hard Filter

检查：

```text
Capability
Input Availability
Semantic Compatibility
Unit Compatibility
Spatial Scale
Temporal Scale
Geometry
CRS
Required Parameter
Validation Status
```

硬约束失败：

```text
REJECTED
```

不得继续参加推荐排名。

---

## 13.2 Soft Ranking

硬约束通过后，可以根据：

```text
capability match
data availability
scale fitness
validation evidence
runtime cost
user preference
```

排序。

排序权重必须配置化。

---

# 14. Workflow Studio

必须实现可视化工作流编辑器。

支持：

```text
拖拽模型
连接变量
删除连接
编辑参数
设置输入
设置输出
检查错误
保存Workflow
版本化
复制Workflow
运行Workflow
```

节点必须显示：

```text
模型名称
版本
状态
输入
输出
```

---

# 15. Workflow科学校验

运行前至少检查：

```text
变量语义
单位
空间参考
时间范围
空间尺度
时间尺度
数据类型
Geometry
缺失值
参数范围
上下游依赖
循环依赖
```

一般 Workflow 必须为 DAG。

如果未来需要反馈耦合：

必须使用：

```text
IterativeGroup
```

显式表示：

```text
iteration
convergence_threshold
max_iterations
```

不得通过普通循环边偷偷形成无限环。

---

# 16. 场景化模型接口器

这是核心科研成果二。

负责：

```text
实际场景
→
实际数据
→
模型输入
```

以及：

```text
模型结果
→
地理实体
→
管理结果
```

---

# 17. Scene Workspace

实现地图中心的场景工作台。

用户必须能够：

```text
新建场景
绘制AOI
上传AOI
选择地理实体
选择时间
设置情景参数
选择数据
查看数据覆盖
运行预检
执行工作流
查看结果
```

---

# 18. 地理实体体系

实现：

```text
GeographicEntity
```

至少支持：

```text
coast_segment
wetland
land_parcel
administrative_unit
management_unit
water_body
protection_zone
custom
```

实体必须：

```text
id
type
geometry
version
valid_from
valid_to
properties
```

必须区分：

```text
Result Object ID
Geographic Entity ID
Management Unit ID
```

不得混为同一个ID。

---

# 19. 数据目录

Data Catalog必须提供：

```text
上传数据
登记URL
登记数据库
登记HTTP服务
搜索
过滤
预览
质量检查
版本
血缘
权限
```

支持至少：

```text
GeoTIFF
COG
GeoJSON
Shapefile
GeoPackage
CSV
NetCDF
JSON
```

---

# 20. 变量语义映射

实现标准变量字典。

例如：

```text
sea_level
elevation
population
land_cover
temperature
salinity
wave_height
precipitation
wind_speed
```

支持：

```text
alias
synonym
approved_mapping
```

自动映射优先级：

```text
Exact Standard Name
↓
Approved Mapping
↓
Ontology/Synonym
↓
Manual Confirmation
```

LLM建议的映射不得直接作为正式映射。

必须经过 Validation Engine。

---

# 21. 单位转换

采用：

```text
Pint
```

完成维度兼容单位转换。

例如：

```text
mm → m
km² → m²
hour → second
```

维度不一致必须阻止运行。

---

# 22. CRS处理

采用：

```text
PyProj
Rasterio
GeoPandas
```

实现水平坐标转换。

必须检查：

```text
CRS missing
CRS mismatch
projection validity
```

---

# 23. 垂向基准

必须设计：

```text
vertical_datum
```

字段和校验机制。

如果：

```text
DEM vertical datum
!=
water level vertical datum
```

且没有有效转换模型：

必须：

```text
BLOCK EXECUTION
```

不能假设两者都以米为单位就一致。

本项目可以不内置全国所有垂向转换格网。

但必须：

```text
有完整元数据
有校验
有转换Adapter接口
有失败阻断
```

---

# 24. 空间尺度转换

根据变量类型选择方法。

至少支持：

## Continuous

```text
nearest
bilinear
cubic
```

## Categorical

默认：

```text
nearest
```

## Extensive quantity

支持：

```text
sum / area weighted aggregation
```

转换方法必须写入 BindingPlan 和 RunManifest。

---

# 25. 时间适配

支持：

```text
nearest
mean
sum
min
max
interpolation
```

必须依据变量的：

```text
aggregation_type
```

决定允许操作。

例如：

```text
precipitation accumulation
```

与：

```text
temperature average
```

不能使用相同默认规则。

---

# 26. 模型运行适配器

必须实现统一：

```text
ModelAdapter
```

接口。

至少：

```text
prepare()
validate()
execute()
collect()
cleanup()
```

必须实现以下适配器。

---

## 26.1 PythonFunctionAdapter

运行本地 Python 模型。

---

## 26.2 CLIAdapter

运行命令行模型。

---

## 26.3 DockerAdapter

运行容器化模型。

---

## 26.4 HTTPAdapter

调用外部 REST API 模型。

---

## 26.5 RasterGISAdapter

处理：

```text
raster calculator
zonal statistics
buffer
intersection
overlay
reprojection
resampling
polygonize
```

---

## 26.6 MLAdapter

处理：

```text
scikit-learn
joblib model
```

---

# 27. 不得伪造外部科学模型

项目研究材料可能已有大量模型目录和既有模型成果。

如果当前代码环境中没有某个模型真实：

```text
源代码
可执行文件
容器
API
模型权重
```

禁止编造一个同名模型并声称已经集成。

必须表示为：

```text
REGISTERED_METADATA
NOT_EXECUTABLE
```

同时提供 Adapter 接入能力。

这是一条强制科研诚信约束。

---

# 28. 内置可实际运行的科研示范模型

为了保证系统独立运行和验收，必须实现一批真实可执行的示范组件。

至少包括以下内容。

---

## 28.1 Weighted Composite Assessment

实现：

```text
positive indicator normalization
negative indicator normalization
manual weight
equal weight
weighted aggregation
classification
```

---

## 28.2 Entropy Weight

实现熵权法。

输出：

```text
weights
normalized matrix
composite score
```

---

## 28.3 TOPSIS

实现标准 TOPSIS。

---

## 28.4 Zonal Statistics

支持：

```text
count
sum
mean
min
max
std
area
percentage
```

---

## 28.5 Raster Calculator

支持安全表达式计算。

禁止直接裸 `eval()`。

---

## 28.6 Sea Level Rise Screening Model

实现一个明确标记为：

```text
Screening / Demonstration Model
```

的 DEM + Sea Level 场景筛查模型。

至少支持：

```text
DEM
sea_level_increment
coastal connectivity
nodata mask
```

输出：

```text
potential inundation raster
potential inundation polygon
area statistics
```

必须在UI和文档中明确：

**该模型是地形连通性风险筛查模型，不得宣称为二维/三维水动力模拟。**

---

## 28.7 Random Forest Model

实现一个通用：

```text
classification/regression
```

ML模型示范。

支持：

```text
train
save
load
predict
metrics
feature importance
```

---

## 28.8 Spatial Suitability Model

实现：

```text
constraint mask
weighted factors
suitability score
classification
```

---

# 29. 可持续发展状态综合评价模块

建立：

# Assessment Center

---

## 29.1 Indicator Definition

字段：

```text
indicator_id
name
category
unit
direction
source
formula
normalization
weight_method
weight
```

---

## 29.2 指标分类

内置示范：

```text
资源利用
空间潜力
脆弱性
稳定性
发展韧性
```

仅作为：

```text
DEMO FRAMEWORK
```

不能声称为唯一评价体系。

---

## 29.3 时间动态评价

至少支持：

```text
T1
T2
...
Tn
```

输出：

```text
score
rank
change
trend
```

---

## 29.4 空间评价

支持：

```text
management unit
administrative unit
custom polygon
grid
```

---

# 30. 多主体协同管理示范

建立轻量：

# Collaboration / Scenario Comparison

角色：

```text
RESEARCHER
MANAGER
PUBLIC
ADMIN
```

每个角色可以拥有：

```text
objective weights
constraints
comments
proposal
```

实现：

```text
方案版本
方案比较
约束冲突检测
意见记录
审核状态
```

不得让系统自动替代真实政策决定。

系统只提供：

```text
事实
模型结果
方案差异
约束冲突
```

---

# 31. 空间优化示范

实现一个可执行研究示范模型：

```text
SpatialOptimizationModel
```

输入：

```text
candidate units
benefit
ecological cost
risk
budget
area requirement
hard constraints
```

输出：

```text
selected units
objective values
constraint satisfaction
```

可以采用：

```text
MILP
```

或可靠的约束优化方法。

必须确保：

```text
hard constraint
```

不可被目标函数得分抵消。

---

# 32. Provenance / 科研追溯

每个结果必须回答：

```text
是谁运行
什么时候运行
什么场景
用了什么数据
数据什么版本
用了什么模型
模型什么版本
用了什么参数
做了什么转换
产生了什么结果
```

前端必须提供：

# Provenance Viewer

---

# 33. 结果版本管理

Result不得被后续运行静默覆盖。

必须：

```text
Result
ResultRevision
ResultManifest
```

不同运行结果必须独立存在。

---

# 34. 质量状态

至少：

```text
RAW
VALIDATED
REVIEWED
PUBLISHED
REJECTED
```

同时区分：

```text
Execution Status
Scientific Validation Status
Review Status
```

不能用一个：

```text
SUCCESS
```

代表全部可信。

---

# 35. Web前端页面

必须完成完整可用UI。

至少包括：

```text
/login
/dashboard

/models
/models/:id

/knowledge-graph

/planner

/workflows
/workflows/:id

/scenes
/scenes/:id

/data

/assessments

/runs
/runs/:id

/results
/results/:id

/research

/admin
```

---

# 36. Dashboard

展示：

```text
场景数量
模型数量
可执行模型数量
工作流数量
最近运行
运行状态
数据资产数量
结果数量
质量状态
```

不得只做静态数字。

---

# 37. Model Center

包括：

```text
模型列表
模型类型
版本
验证状态
执行状态
输入
输出
参数
约束
模型详情
模型关系
测试运行
```

---

# 38. Smart Planner

UI：

左侧：

```text
自然语言任务输入
```

中部：

```text
结构化任务拆解
```

右侧：

```text
候选模型
缺失数据
约束
推荐依据
```

允许：

```text
生成Workflow
```

---

# 39. Workflow Studio

使用可视化图。

显示：

```text
Data Node
Transform Node
Model Node
Validation Node
Output Node
```

错误必须直接显示在对应节点/连接上。

---

# 40. Scene Workspace

地图为核心。

左侧：

```text
Scene Tree
Data
Entity
Layer
```

中部：

```text
Map
```

右侧：

```text
Scene Config
Bindings
Parameters
Validation
```

底部：

```text
Job Status
Log
```

---

# 41. Run Center

显示：

```text
Queued
Running
Succeeded
Failed
Cancelled
```

必须支持：

```text
cancel
retry
view logs
view manifest
```

---

# 42. Result Center

必须支持：

```text
地图
图层
表格
统计图
时间序列
场景比较
下载
Provenance
```

---

# 43. Research Evaluation页面

必须把科研实验也实现为系统能力。

至少允许运行：

## Experiment A

```text
Rule-only Planner
```

## Experiment B

```text
LLM-only Recommendation
```

## Experiment C

```text
LLM + Knowledge Graph + Constraint Validation
```

统计：

```text
workflow validity rate
constraint violation rate
manual correction count
planning latency
```

---

# 44. 场景接口实验

测试：

```text
正确单位
错误单位
正确CRS
错误CRS
缺CRS
缺时间
缺数据
错误语义
尺度不匹配
```

输出：

```text
detected
blocked
auto-fixed
manual-review
```

统计：

```text
binding success rate
error detection rate
automatic adaptation rate
manual intervention rate
```

---

# 45. 数据库

至少需要实现以下实体表。

```text
users
roles

projects

models
model_versions
model_variables
model_parameters
model_constraints

data_assets
data_asset_versions

geographic_entities
entity_versions

scenes
scene_versions

workflows
workflow_versions
workflow_nodes
workflow_edges

bindings

jobs
job_nodes
job_logs

results
result_revisions

run_manifests
result_manifests

indicator_frameworks
indicators
assessments
assessment_results

graph_nodes
graph_edges

research_experiments
experiment_runs
experiment_metrics

audit_logs
```

必须使用：

```text
Alembic migration
```

禁止仅靠运行时自动建表。

---

# 46. API

必须建立：

```text
/api/v1
```

至少包括：

## Models

```text
GET    /models
POST   /models
GET    /models/{id}
PUT    /models/{id}
DELETE /models/{id}

POST   /models/{id}/validate
POST   /models/{id}/test
```

---

## Data

```text
GET    /data-assets
POST   /data-assets
GET    /data-assets/{id}
POST   /data-assets/{id}/validate
```

---

## Scenes

```text
GET    /scenes
POST   /scenes
GET    /scenes/{id}
PUT    /scenes/{id}

POST   /scenes/{id}/preflight
```

---

## Planning

```text
POST /planner/parse
POST /planner/recommend
POST /planner/build-workflow
```

---

## Workflows

```text
GET  /workflows
POST /workflows

GET  /workflows/{id}

POST /workflows/{id}/validate
POST /workflows/{id}/run
```

---

## Jobs

```text
GET  /jobs
GET  /jobs/{id}

POST /jobs/{id}/cancel
POST /jobs/{id}/retry
```

---

## Results

```text
GET /results
GET /results/{id}

GET /results/{id}/provenance
```

---

## Assessment

```text
POST /assessments
POST /assessments/{id}/run
GET  /assessments/{id}/results
```

---

## Knowledge Graph

```text
GET /graph
GET /graph/models/{id}
GET /graph/variables/{id}
```

---

# 47. GeoAI集成接口

必须单独建立：

```text
integration/geoai
```

不得成为系统运行依赖。

提供：

```text
GET  /api/v1/integration/capabilities
GET  /api/v1/integration/models

POST /api/v1/integration/jobs
GET  /api/v1/integration/jobs/{id}

GET  /api/v1/integration/results/{id}
```

同时提供：

```text
docs/geoai-integration.md
```

说明以后 GeoAI 如何：

```text
注册 CoastMAS
查询模型
提交场景
执行Workflow
获得结果
```

---

# 48. 示例数据

必须创建：

```text
sample-data/
```

所有样例明确标注：

```text
SYNTHETIC / DEMONSTRATION DATA
```

至少包括：

```text
coastal_aoi.geojson

management_units.geojson

dem.tif

land_cover_t1.tif
land_cover_t2.tif

population.csv

economic.csv

tide.csv

protection_zone.geojson
```

如果不方便生成真实 GeoTIFF：

必须使用程序生成真正可读取的 GeoTIFF，而不是伪文件。

---

# 49. 内置完整演示场景

必须至少完成以下三个完整场景。

---

## Scenario A  
### 海平面上升潜在淹没与影响分析

```text
Scene
↓
DEM
↓
Sea Level Screening
↓
Potential Inundation
↓
Population / Land Use Overlay
↓
Management Unit Statistics
↓
Result
```

---

## Scenario B  
### 海岸带资源利用与空间潜力综合评价

```text
Indicators
↓
Normalization
↓
Weight
↓
Composite Evaluation
↓
Spatial Unit Result
↓
Map
```

---

## Scenario C  
### 多期发展韧性动态评价

```text
T1
T2
T3
↓
Indicator Engine
↓
Composite Score
↓
Change
↓
Trend
↓
Spatial Comparison
```

---

# 50. 第一个真正体现两个“器”的完整示范

系统必须支持用户输入：

```text
分析研究区在0.5米海平面上升情景下，
潜在淹没范围及其对人口和土地利用的影响，
并按管理单元统计。
```

系统自动：

```text
1. 解析目标

2. 拆解任务

3. 找到：
   DEM
   海平面场景
   人口
   土地利用
   管理单元

4. 找到：
   SeaLevelScreening
   Overlay
   ZonalStatistics

5. 生成Workflow

6. 校验单位、CRS、变量

7. 生成BindingPlan

8. 运行

9. 生成地图和表格

10. 保存RunManifest

11. 保存ResultManifest

12. 展示Provenance
```

此场景必须完成真正端到端 E2E 测试。

---

# 51. 权限

至少实现：

```text
ADMIN
RESEARCHER
MANAGER
VIEWER
```

权限范围：

```text
model
data
scene
workflow
job
result
publish
```

---

# 52. 审计

所有重要修改写入：

```text
audit_logs
```

包括：

```text
who
when
action
resource
old_value
new_value
```

---

# 53. 科研可复现要求

所有随机算法必须支持：

```text
random_seed
```

所有运行必须记录：

```text
code version
model version
data version
parameter
environment
```

---

# 54. 错误处理

禁止：

```text
catch(Exception)
然后返回“未知错误”
```

至少建立：

```text
ValidationError
DataError
ModelError
ExecutionError
BindingError
ConstraintError
AuthorizationError
```

前端显示用户可理解的错误信息。

开发日志保留技术堆栈。

---

# 55. 安全

至少：

```text
password hashing
JWT/session security
RBAC

upload validation
path traversal prevention

safe subprocess
container isolation

SQL injection prevention
XSS prevention

API validation
```

Raster Calculator 禁止任意 Python 执行。

CLIAdapter 必须限制命令模板，不允许用户直接输入任意系统命令。

---

# 56. 性能

目标：

元数据 API：

```text
P95 < 500 ms
```

普通地图查询：

```text
P95 < 1 s
```

长时间模型：

必须异步。

禁止：

```text
HTTP同步等待几十分钟
```

---

# 57. 前端专业性

不是科研Demo页面。

界面需要达到：

```text
专业GIS / 数据分析工作台
```

标准。

必须：

- 清晰层级；
- 地图中心；
- 工作流交互；
- 状态反馈；
- 错误定位；
- 结果比较；
- 可追溯；
- 响应式。

不追求花哨动画。

---

# 58. 自动测试

Backend至少：

```text
unit tests
integration tests
API tests
workflow tests
binding tests
model adapter tests
```

Frontend至少：

```text
component tests
critical interaction tests
```

E2E采用：

```text
Playwright
```

---

# 59. 必测错误场景

自动测试至少覆盖：

```text
缺数据
单位不兼容
CRS不一致
CRS缺失
参数越界
模型不存在
模型不可执行
Workflow断链
Workflow循环
任务失败
任务取消
结果版本
权限不足
```

---

# 60. E2E验收

必须自动完成：

```text
Login
↓
Create Scene
↓
Select AOI
↓
Select Demo Data
↓
Enter Natural Language Goal
↓
Generate Workflow
↓
Validate
↓
Run
↓
Wait for Completion
↓
Open Result
↓
View Map
↓
View Statistics
↓
View Provenance
```

---

# 61. Docker验收

任务结束前必须实际执行：

```bash
docker compose build
docker compose up -d
```

检查：

```text
frontend healthy
backend healthy
database healthy
redis healthy
object storage healthy
knowledge graph healthy
worker healthy
```

---

# 62. 数据库验收

实际运行：

```text
migration up
migration down test
migration up
```

至少验证：

```text
fresh install
```

可以成功。

---

# 63. 必须输出OpenAPI

FastAPI：

```text
/openapi.json
/docs
```

必须可用。

---

# 64. 文档

必须交付：

```text
README.md

docs/
    architecture.md
    scientific-method.md
    model-spec.md
    scene-spec.md
    workflow-spec.md
    binding-engine.md
    knowledge-graph.md
    llm-agent.md
    adapter-development.md
    assessment-engine.md
    api.md
    deployment.md
    user-guide.md
    admin-guide.md
    research-validation.md
    geoai-integration.md
    acceptance-report.md
```

---

# 65. 科研方法文档

`scientific-method.md`

必须明确区分：

```text
Scientific Model
Engineering Adapter
LLM Recommendation
Scientific Validation
User Review
```

明确说明：

> LLM负责理解和编排，不替代专业模型科学机理。

---

# 66. 研发边界说明

README必须明确：

本系统实现：

```text
智能模型组织
数据-模型适配
工作流执行
动态评价
科研验证
```

不得声称：

```text
自动拥有所有海岸带模型
自动取代水动力专家
所有地区无需校准
所有数据可自动融合
AI生成结果天然科学可信
```

---

# 67. 不允许出现的交付问题

最终仓库不得存在以下情况。

## 禁止一

```text
TODO
FIXME
pass
NotImplemented
```

出现在核心必选链路。

---

## 禁止二

按钮无法使用。

---

## 禁止三

页面只有UI，没有后端。

---

## 禁止四

API存在，但没有UI。

---

## 禁止五

数据库表设计了，但程序不用。

---

## 禁止六

知识图谱只是截图。

---

## 禁止七

LLM只是聊天窗口。

---

## 禁止八

Workflow只能看，不能运行。

---

## 禁止九

演示数据是假扩展名。

---

## 禁止十

模型结果无法追溯。

---

# 68. 研究实验必须真正执行

完成代码后必须运行科研验证。

至少完成：

## Test 1

任务拆解正确性。

## Test 2

模型选择硬约束。

## Test 3

知识图谱模型连接。

## Test 4

单位错误检测。

## Test 5

CRS错误检测。

## Test 6

缺失数据检测。

## Test 7

Workflow自动生成。

## Test 8

Workflow完整执行。

## Test 9

场景Binding。

## Test 10

结果实体化。

## Test 11

动态综合评价。

## Test 12

科研复现。

生成：

```text
research-validation.md
```

并附真实执行结果。

---

# 69. 项目目录

建议最终：

```text
coastmas/

├── apps/
│   ├── web/
│   └── api/
│
├── services/
│   ├── worker/
│   └── graph/
│
├── packages/
│   ├── orchestration-core/
│   ├── scene-engine/
│   ├── model-sdk/
│   ├── adapter-sdk/
│   ├── assessment-engine/
│   └── coastal-domain/
│
├── models/
│   ├── statistical/
│   ├── raster/
│   ├── ml/
│   └── screening/
│
├── sample-data/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── research/
│
├── docs/
│
├── scripts/
│
├── docker/
│
├── docker-compose.yml
├── .env.example
└── README.md
```

可根据框架规范调整。

但必须保持：

```text
core
domain
adapter
app
```

逻辑解耦。

---

# 70. GeoAI代码边界

如果当前工作目录存在：

```text
GeoAI Platform
```

代码：

不要直接修改。

创建独立：

```text
coastmas/
```

项目。

GeoAI只通过：

```text
HTTP API
Adapter
```

未来接入。

---

# 71. Git要求

开始研发后：

```text
初始化Git
```

保持合理commit历史。

最终：

```text
git status
```

必须干净。

不得把：

```text
.env
password
token
large generated data
```

提交Git。

---

# 72. 最终Definition of Done

只有同时达到以下条件才允许宣布完成。

```text
[ ] 系统可以独立启动

[ ] 用户可以登录

[ ] Model Center可用

[ ] ModelSpec可管理

[ ] 知识图谱可用

[ ] Smart Planner可用

[ ] 管理目标可拆解

[ ] 模型可检索

[ ] Workflow可以自动生成

[ ] Workflow可以人工编辑

[ ] Workflow可以校验

[ ] Workflow可以运行

[ ] Model Adapter体系可用

[ ] Scene Workspace可用

[ ] Data Catalog可用

[ ] SceneSpec可用

[ ] BindingPlan可生成

[ ] 单位转换可用

[ ] CRS检查可用

[ ] 垂向基准检查存在

[ ] 时间适配可用

[ ] 数据空间适配可用

[ ] 运行中心可用

[ ] 结果中心可用

[ ] Provenance完整

[ ] 动态综合评价可用

[ ] 空间优化示范可用

[ ] 多主体协同示范可用

[ ] 三个科研Demo可运行

[ ] LLM不可用时系统仍可运行

[ ] Research Evaluation可运行

[ ] 自动化测试通过

[ ] E2E通过

[ ] docker compose启动成功

[ ] OpenAPI正常

[ ] 文档完整

[ ] GeoAI Adapter完成

[ ] acceptance-report.md完成

[ ] 核心链路没有TODO/placeholder
```

任何一项未完成：

不得声明项目研发完成。

---

# 73. 最终验收报告

生成：

```text
docs/acceptance-report.md
```

内容必须包括：

```text
1 项目概况

2 实际完成模块

3 软件架构

4 数据库

5 模型数量

6 可执行模型数量

7 Adapter数量

8 API数量

9 页面数量

10 自动测试数量

11 测试通过率

12 E2E结果

13 科研实验结果

14 Demo场景结果

15 Docker运行状态

16 已知限制

17 外部模型待接入清单

18 GeoAI集成方式
```

不允许隐藏未完成内容。

---

# 74. 最终向用户汇报格式

任务结束后，不要只说：

> 已完成。

必须报告：

```text
A. 最终版本

B. Git commit

C. 项目路径

D. 启动方式

E. Web地址

F. API地址

G. 测试结果

H. 研究实验结果

I. 核心功能矩阵

J. Demo账号

K. Demo场景

L. 文档位置

M. GeoAI集成接口

N. 明确列出尚未接入的外部模型
```

---

# 75. 最高优先级研发原则

整个研发过程中始终遵守：

## 原则一

**这是科研软件，不允许为了“看起来完成”而伪造科学能力。**

## 原则二

**没有真实模型程序的模型只能注册元数据和Adapter，不能伪装成已经接入。**

## 原则三

**LLM不能绕过科学约束。**

## 原则四

**所有正式结果必须可复现、可追溯。**

## 原则五

**项目必须独立于GeoAI运行。**

## 原则六

**通用核心必须能够未来被GeoAI复用。**

## 原则七

**本任务必须完成软件，而不仅仅完成设计。**

## 原则八

**不要向用户请求下一阶段任务。**

如果实施中发现局部设计需要调整：

自行选择工程上更合理、科研上更严谨的方案，

记录到：

```text
docs/architecture-decisions.md
```

继续实施。

---

# 76. 任务启动指令

现在立即开始研发。

第一步可以审计当前工作目录和运行环境，但审计只是实施准备，不是最终任务。

如果当前目录不是 CoastMAS 项目：

创建独立项目。

然后连续完成：

```text
Architecture
→
Database
→
Backend
→
Core
→
Adapters
→
Knowledge Graph
→
LLM Agent
→
Scene Engine
→
Assessment
→
Frontend
→
Demo Data
→
Research Experiments
→
Tests
→
E2E
→
Docker
→
Documentation
→
Acceptance
```

这些只是你的**内部执行顺序**。

不要把它们变成需要用户逐项确认的外部开发阶段。

最终只有在：

# Definition of Done 全部满足

之后，才向用户提交最终研发结果。