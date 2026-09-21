# CoastMAS

独立的海岸带管理与科研工作空间。当前本机入口：[打开 CoastMAS](http://127.0.0.1:58000)。项目仍在持续研发，**全范围统一验收尚未完成**；实际状态与证据见[验收报告](docs/acceptance-report.md)和[研发状态](docs/STATE.md)。

当前可使用模型与数据目录、地图场景、工作流编辑与预检、独立worker执行、版本化结果及溯源、评价体系、协同方案、空间优化、科研规划对照和管理员界面。默认工作区展示黄河口、胶州湾、长江口三个真实公开影像演示。全部科学解释以模型声明、数据来源和下列方法文档为准。

| 任务 | 操作与限制 |
|---|---|
| 启动、配置及验证 | [Web运行](docs/web-runtime.md)、[基础设施恢复](docs/object-storage-recovery.md) |
| 真实影像和互联网底图 | [三个真实影像演示](docs/real-imagery-demos.md) |
| 账号、权限、归档与独立测试 | [系统管理](docs/admin-and-testing.md) |
| 模型及数据 | [模型中心](docs/model-center.md)、[数据工作区](docs/data-workspace.md)、[数据源](docs/data-sources.md) |
| 场景和工作流 | [地图场景](docs/scene-workspace.md)、[工作流编辑](docs/workflow-studio.md)、[规划提供方](docs/planning-and-providers.md) |
| 结果、评价与决策 | [结果中心](docs/result-center.md)、[评价体系](docs/assessment-center.md)、[协同](docs/collaboration.md)、[优化](docs/spatial-optimization.md) |
| 科研规划对照 | [科研评估及统计分母](docs/research-evaluation.md) |
| 开发与验收依据 | [架构](docs/architecture.md)、[执行质量](docs/execution-quality.md)、[完整需求映射](docs/requirements-traceability.csv) |

账号口令及服务密钥只保存在私有配置中，不在仓库或本文提供通用默认密码。已归档项目保留历史和权限；归档不是删除，也不是撤权。自动化浏览器测试使用独立资源，避免污染日常界面。

当前完整容器应用部署与统一验收入口仍待补齐，请遵循已验证的本机运行文档，不把基础设施容器健康当作全产品部署验收。
