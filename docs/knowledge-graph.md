# 模型知识图谱

`KnowledgeGraphService` 从当前项目 PostgreSQL 中的不可变模型、数据、场景和工作流版本构造图，使用 NetworkX 进行有界邻域遍历。资源版本表是唯一事实来源，不另建会与目录漂移的图数据副本，不部署 Neo4j。该实现遵循 EQ-1.0 的 PostgreSQL 关系数据＋NetworkX 选型；节点与关系对应可追溯的契约字段和明确版本。

## 节点与关系语义

节点包括 Objective、Task、Model、Variable、DataType、EntityType、SceneType、Constraint，以及实际 DataAsset、Scene、Workflow。稳定节点标识由类型和规范 JSON 内容摘要生成；资源节点另保留原资源 ID 和版本。相同科学变量可以共享语义节点，端口名称保留在边属性；单位、维度、空间/时间支撑、聚合、NoData 语义均参与变量身份。

| 关系 | 来源及含义 |
|---|---|
| REQUIRES | 模型输入/约束、场景目标/约束、工作流步骤 |
| PRODUCES | 模型输出、数据资产提供的实际声明变量 |
| SUPPORTS | 模型明确声明的能力任务 |
| DEPENDS_ON | 保存工作流中的下游步骤依赖上游步骤 |
| MAPS_TO | 变量的数据类型或工作流已保存数据绑定，保留端口和完整 BindingPlan |
| VALID_FOR | 场景声明的实体类型、工作流场景类型 |
| INCOMPATIBLE_WITH | 相同标准名但维度或语义类别矛盾的变量，维度经 Pint 解析比较 |
| DERIVED_FROM | 工作流步骤来源于固定模型版本 |
| CAN_FOLLOW | 来源模型输出与目标模型输入具有完全相同科学变量契约；目标是候选下游 |

CAN_FOLLOW 是 `contract_candidate`，必须再次执行共享科学预检；不能据此声称数据覆盖、坐标/垂向基准、时间尺度或运行注册已通过。保存工作流中的关系标为 `workflow_declaration`，也不冒充执行成功。普通声明与明确冲突另有证据类型。不存在依据的关系不凭空补造来填满图谱。

工作流历史模型引用可显示为只含标识/版本的来源节点；不把旧版本自动替换为当前模型。模型运行配置、数据存储 URI、凭证及用户会话不进入图响应。

## 查询与界面

`GET /api/v1/knowledge-graph?project_id=...` 返回当前可见、未归档且启用资源的关系投影；`focus` 指定稳定节点 ID，`depth=0..4` 查询邻域。遍历为双向邻域，以便从输入变量找到提供它的数据；返回边仍保留原方向。每次读取重新检查项目权限和资源版本 checksum，响应不缓存。

目录上限 500 个资源版本，图最多 10000 节点和 50000 边，相同标准名的冲突比较最多 250000 对。超预算明确返回错误，不静默截断后声称完整。视图超过 300 节点时要求选择中心或减少深度；关系表每页 100 条，不隐藏剩余关系。

登录后打开“知识图谱”，默认选择一个模型作为中心。可以切换中心节点、邻域深度和关系类型；点击节点查看来源，再跳转模型/数据/场景/工作流页面。默认缩放优先显示中心模型及直接变量、数据，其他节点可平移缩放查看。候选边使用虚线并在证据表显示仍需预检。

## 依赖与证据

固定 NetworkX 3.6.1，BSD-3-Clause；版本和许可证已核对安装包元数据。[官方最短路径接口文档](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.shortest_paths.generic.shortest_path.html)说明图的有向边语义；本项目邻域使用无向视图进行有界最短距离遍历，原图为 MultiDiGraph。

核心与真实 PG API 测试覆盖目录稳定性、运行配置不泄露、九类关系、科学冲突依据、邻域深度、悬空/重复身份和越权拒绝。真实浏览器 `20260920T132950224396Z-knowledge-graph-focus-browser` 已通过模型→数据→候选下游、深度切换、来源跳转；截图 `artifacts/screenshots/knowledge-graph.png`。完整产品验收、全部场景工作台和最终质量门槛仍独立记录。
