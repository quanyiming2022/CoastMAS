# CoastMAS 架构与实施约束

依据 requirements.md 全部 76 节及 execution-quality.md；需求追踪表保留章节与条目，NOT_RUN 不代表完成。

采用模块化单体 FastAPI API 与独立 Celery worker，共享 src/coastmas 版本化契约。通用 core 不导入海岸带 domain。PostgreSQL/PostGIS 是业务与图谱关系的唯一真源，SQLAlchemy/Alembic 管理外键、版本、权限和迁移。Redis 提供队列；MinIO 管理经校验和验证的不可变产物。React/TypeScript strict 前端使用 MapLibre、React Flow、ECharts。

运行链路：用户及项目授权 → 冻结 Scene/Workflow/Model/Data 版本 → 确定性科学预检 → 原子幂等提交 → worker 执行已注册 Adapter → 暂存与校验 → 不可变结果发布 → 溯源。任务取消、重复投递与发布冲突必须在服务端处理。

首要契约：ModelSpec、VariableSpec、DataAssetSpec、SceneSpec、WorkflowSpec、BindingPlan、ExecutionJob、RunManifest、ResultManifest。所有科学检查先于排名；LLM 只产生经 schema 校验的候选，不能补造数据或模型。

科学示范包括评价/熵权/TOPSIS、GIS、连通性淹没筛查、随机森林、适宜性、空间优化。淹没基准水位与增量分开；NoData 不等于零。动态评价使用固定参考。随机算法冻结种子及训练验证划分。

采用单执行者，按能力增量测试；最终集中复查权限、数据流、竞态、科学边界。真实外部 LLM 实验与确定性演示单独计数。部署未启动、测试未运行或失败均不算通过。
