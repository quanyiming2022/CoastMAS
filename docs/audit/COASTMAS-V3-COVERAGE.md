# CoastMAS V3 实现覆盖矩阵

审计commit：`8d8ae10e8a53c3aa63501c0244b7e37739609c13`。状态按最新审计定义；YES只表示该维度存在，**不表示端到端通过**。COMPONENT为真实数值/数据库/worker组件执行，未当作浏览器链。机器版含各行代码、接口、对象、证据和范围。

## 54项导航

| 中心 | 入口 | 实际路径 | 判定 | 说明 |
|---|---|---|---|---|
| workspace | 工作台 | /research | 存在且可打开（功能范围另评） | 权限：project |
| research | 项目 | /projects | 存在且可打开（功能范围另评） | 权限：project |
| research | 研究内容 | — | 缺失业务入口；仅开发注册 | 权限：project |
| research | 研究任务 | /tasks | 存在且可打开（功能范围另评） | 权限：project |
| research | 任务关系 | — | 缺失业务入口；仅开发注册 | 权限：project |
| data | 数据资源 | /library | 存在且可打开（功能范围另评） | 权限：project |
| data | 数据导入 | — | 缺失业务入口；仅开发注册 | 权限：project |
| data | 数据处理 | — | 缺失业务入口；仅开发注册 | 权限：project |
| data | 数据质量 | — | 缺失业务入口；仅开发注册 | 权限：project |
| methods | 指标库 | /indicators | 存在且可打开（功能范围另评） | 权限：project |
| methods | 标准化方法 | — | 缺失业务入口；仅开发注册 | 权限：project |
| methods | 权重方法 | — | 缺失业务入口；仅开发注册 | 权限：project |
| methods | 综合评价方法 | /methods | 存在且可打开（功能范围另评） | 权限：project |
| methods | 分级方法 | — | 缺失业务入口；仅开发注册 | 权限：project |
| methods | 时空分析方法 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 模型目录 | /models | 真实目录但当前无运行包 | 权限：project；AUDIT-010/011 |
| modelops | 模型接入 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 模型解构 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 模型契约 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 模型测试 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 运行环境 | — | 缺失业务入口；仅开发注册 | 权限：project |
| modelops | 模型版本 | — | 缺失业务入口；仅开发注册 | 权限：project |
| coupling | 数据—模型匹配 | /coupling/matching | 职责放错：任务预检代替Coupler | 权限：project；AUDIT-007 |
| coupling | 模型—模型耦合 | — | 缺失业务入口；仅开发注册 | 权限：project |
| coupling | 数据适配 | — | 缺失业务入口；仅开发注册 | 权限：project |
| coupling | 场景约束 | — | 缺失业务入口；仅开发注册 | 权限：project |
| coupling | 工作流 | — | 缺失业务入口；仅开发注册 | 权限：project |
| coupling | 服务编排 | — | 缺失业务入口；仅开发注册 | 权限：project |
| planning | 规划任务 | /planning/tasks | 存在且可打开（功能范围另评） | 权限：project |
| planning | 规划目标 | /planning/objectives | 存在且可打开（功能范围另评） | 权限：project |
| planning | 约束库 | /planning/constraints | 存在且可打开（功能范围另评） | 权限：project |
| planning | 决策变量 | /planning/decisions | 存在且可打开（功能范围另评） | 权限：project |
| planning | 情景方案 | — | 缺失业务入口；仅开发注册 | 权限：project |
| planning | 优化求解器 | — | 缺失业务入口；仅开发注册 | 权限：project |
| planning | 方案比较 | — | 缺失业务入口；仅开发注册 | 权限：project |
| runs | 当前运行 | — | 缺失业务入口；仅开发注册 | 权限：project |
| runs | 运行队列 | — | 缺失业务入口；仅开发注册 | 权限：project |
| runs | 运行记录 | /runs | 存在且可打开（功能范围另评） | 权限：project |
| runs | 计算资源 | — | 缺失业务入口；仅开发注册 | 权限：project |
| runs | 问题诊断 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 地图成果 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 数据成果 | /results | 存在且可打开（功能范围另评） | 权限：project |
| results | 模拟成果 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 规划成果 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 时空分析 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 方案比较 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 报告 | — | 缺失业务入口；仅开发注册 | 权限：project |
| results | 服务发布 | — | 缺失业务入口；仅开发注册 | 权限：project |
| management | 用户与权限 | /management/users | 存在且可打开（功能范围另评） | 权限：systemOnly |
| management | 项目成员 | — | 缺失业务入口；仅开发注册 | 权限：manage |
| management | 扩展管理 | — | 缺失业务入口；仅开发注册 | 权限：manage |
| management | 系统设置 | /management/settings | 存在且可打开（功能范围另评） | 权限：systemOnly |
| management | 审计 | /management/audit | 存在且可打开（功能范围另评） | 权限：manage |
| management | 回收站 | — | 缺失业务入口；仅开发注册 | 权限：manage |

## 四类任务32步骤

| 类型 | 步骤 | 当前组件／接口 | 产物与实际执行边界 | 状态 | 问题 |
|---|---|---|---|---|---|
| assessment | 1 数据 · 待补 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| assessment | 2 准备与对齐 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| assessment | 3 指标 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| assessment | 4 权重与评价 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-005 |
| assessment | 5 综合计算 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-005 |
| assessment | 6 分级 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-005 |
| assessment | 7 时空分析 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-005 |
| assessment | 8 成果 · 待验证 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| simulation | 1 数据 · 待补 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-003 |
| simulation | 2 准备与对齐 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-003 |
| simulation | 3 状态变量 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-003 |
| simulation | 4 模型 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-003 |
| simulation | 5 情景条件 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-003 |
| simulation | 6 模拟运行 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-003 |
| simulation | 7 情景分析 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-003 |
| simulation | 8 成果 · 待验证 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-003 |
| planning | 1 数据 · 待补 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| planning | 2 准备与对齐 · 待核查 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| planning | 3 现状诊断 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-012 |
| planning | 4 规划目标 · 待配置 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| planning | 5 约束与决策变量 · 待配置 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| planning | 6 方案生成与优化 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-012 |
| planning | 7 方案评价与比较 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-012 |
| planning | 8 规划成果 · 待验证 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL |  |
| comparison | 1 选择方案 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 2 统一比较口径 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 3 评价指标 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 4 统计分析 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 5 空间差异 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 6 权衡分析 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 7 敏感性分析 · 未接通 | ResearchStepPanel 未接通分支；没有领域编辑器；NONE（该步骤无操作API连接） | NONE；仅打开步骤，无业务执行 | UI_ONLY | AUDIT-004 |
| comparison | 8 比较成果 · 待验证 | ResearchStepPanel(validation) + ResultArtifact / ResearchWorkspace；GET /api/jobs/{id}/result；/api/jobs/{id}/artifacts/{artifact}/download；旧/files/{index}存在500 | 固定Run实际空间/表格产物；NDVI与规划单元已测。缺完整模拟/优化/比较上游时没有相应最终成果 | PARTIAL | AUDIT-004 |

## 177项算法/能力

| 设计能力 | 代码存在 | API存在 | DB存在 | UI存在 | 真实执行 | 测试 | 状态 | 问题ID |
|---|---|---|---|---|---|---|---|---|
| `data.reproject` 投影转换 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.align_grid` 网格对齐 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.resample` 重采样 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.clip` 裁剪 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.mosaic` 镶嵌 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.mask` 掩膜 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.rasterize` 栅格化 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.vectorize` 分类栅格矢量化 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.spatial_join` 空间连接 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.attribute_join` 属性连接 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.aggregate` 空间/分组聚合 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.unit_convert` 单位换算 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.temporal_align` 时间适配 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.reclassify` 类别重分类 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.interpolate` 空间/时间插值 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.buffer` 缓冲 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.distance` 最近距离 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.geometry_ops` 相交、融合、面积、长度与几何校验 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.density` 道路/POI密度与核密度 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `data.zonal_stats` 分区统计/面积比例 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.table_formula` 字段表达式/条件/人均/比例 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-018 |
| `data.csv_intelligence` 非统一CSV/年鉴解析 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 适用已有profile | PASS | PARTIAL | AUDIT-018,AUDIT-028 |
| `spatialize.join` 行政区关联 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-019 |
| `spatialize.area` 有效面积分配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-019 |
| `spatialize.prior` 先验约束分配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-019 |
| `spatialize.regression` 回归辅助空间化 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-019 |
| `spatialize.sector` 分产业空间化 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-019 |
| `indicator.ndvi` NDVI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | VERIFIED | AUDIT-025 |
| `indicator.evi` EVI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | PARTIAL | AUDIT-025 |
| `indicator.savi` SAVI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | PARTIAL | AUDIT-025 |
| `indicator.ndwi` NDWI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | PARTIAL | AUDIT-025 |
| `indicator.mndwi` MNDWI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | PARTIAL | AUDIT-025 |
| `indicator.ndbi` NDBI | YES | YES/受限 | YES/通用记录 | YES/受限 | YES — 实际worker | PASS | PARTIAL | AUDIT-025 |
| `indicator.water_fraction` 水体比例 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.wetland_fraction` 湿地比例 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.ecoland_fraction` 生态用地比例 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.lst` LST地表温度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.fvc` FVC植被覆盖度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.npp` NPP净初级生产力 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.habitat_quality` 生境质量 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.connectivity` 生态连通性 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.soil_retention` 土壤保持 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.carbon` 碳储量/碳汇 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.landuse_intensity` 土地利用强度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.landuse_dynamic` 土地利用动态度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.built_fraction` 建设用地比例 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.urban_speed` 城市扩张速度 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 测试中的真实worker/核函数 | PASS | PARTIAL | AUDIT-025 |
| `indicator.urban_intensity` 城市扩张强度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.urban_efficiency` 城市扩张效率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.lei` 景观扩张指数LEI | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.compactness` 紧凑度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.patch_density` 斑块密度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.edge_density` 边界密度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.fragmentation` 景观破碎度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.road_density` 道路密度 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 测试中的真实worker/核函数 | PASS | PARTIAL | AUDIT-025 |
| `indicator.population_density` 人口密度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.population_growth` 人口增长率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.gdp_density` GDP密度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.gdp_growth` GDP增长率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.secondary_share` 第二产业比重 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.tertiary_share` 第三产业比重 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.industrial_added_value` 工业增加值 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.port_throughput` 港口吞吐 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.energy` 能源消费 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.fiscal_revenue` 财政收入 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.fixed_investment` 固定资产投资 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.tourism_intensity` 旅游强度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.elevation` 海拔/高程 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.slope` 坡度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.coast_distance` 距海岸 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.river_distance` 距河流 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.hazard_frequency` 历史灾害频率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.heavy_rain` 暴雨指标 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.population_exposure` 人口暴露 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.gdp_exposure` GDP暴露 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.building_exposure` 建筑暴露 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.road_exposure` 道路暴露 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.surge_depth` 风暴潮淹没深度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.slr` 海平面上升情景 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.vulnerability` 生态/社会脆弱性 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.resilience` 恢复力 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.shoreline_rate` 岸线变化率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.shoreline_intensity` 岸线利用强度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.natural_shoreline` 自然岸线保有率 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.wetland_change` 滨海湿地变化 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.reclamation` 围填海强度 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.water_quality` 近岸水质 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.erosion` 海岸侵蚀 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `indicator.marine_sensitivity` 海洋生态敏感性 | YES | YES/受限 | NO | YES/受限 | NO | NOT_RUN | REGISTERED_ONLY | AUDIT-008 |
| `score.minmax` Min-Max评分 | YES | YES/受限 | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `score.zscore` Z-score | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `score.target` 适度/目标区间 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `score.piecewise` 分段评分 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `score.category` 类别评分 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `score.membership` 隶属函数 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `score.standard` 行业标准阈值评分 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `score.custom` 自定义评分 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `weight.ahp` 层次分析AHP | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.delphi` Delphi专家赋权 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `weight.manual` 专家直接/手工权重 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.equal` 显式等权基准 | YES | NO | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.combined` 组合赋权 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `weight.entropy` 熵权法 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.critic` CRITIC | YES | NO | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.cv` 变异系数赋权 | YES | NO | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.std` 标准差赋权 | YES | NO | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.correlation` 相关性权重 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `weight.pca` PCA主成分评价 | YES | NO | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `weight.factor` 因子分析 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `weight.projection_pursuit` 评价型投影寻踪 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.wlc` 加权线性综合 | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `evaluate.topsis` TOPSIS | YES | YES/受限 | YES/通用记录 | YES/受限 | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005 |
| `evaluate.fuzzy` 模糊综合评价 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.grey` 灰色关联 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.ideal_point` 理想点法 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.coordination` 耦合协调度 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.obstacle` 障碍度 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.dea` DEA效率 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `evaluate.custom` 自定义评价模型 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `classify.natural_breaks` Jenks Natural Breaks | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `classify.fisher_jenks` Fisher-Jenks | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.fisher_sampled` Fisher-Jenks样本拟合 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `classify.quantile` 分位数 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.equal_interval` 等间隔 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.std` 标准差分级 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.geometric` 几何间隔 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.custom` 自定义阈值 | YES | NO | NO | NO | COMPONENT — 真实数值核函数 | PASS | PARTIAL | AUDIT-005,AUDIT-003 |
| `classify.standard` 行业标准等级 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-005 |
| `stats.area` 等级面积/占比/增减 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.transition` 等级/用地转移矩阵 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.rate` 变化率/年率 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.ols_trend` 线性趋势 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.sen` Sen斜率 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.mann_kendall` Mann-Kendall | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.change_point` 突变检测 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.moran_global` Global Moran I | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.moran_local` Local Moran I | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.getis` Getis-Ord Gi*热点 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.centroid` 重心迁移 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.ellipse` 标准差椭圆 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.heterogeneity` 空间异质性/分组差异 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.gradients` 岸线/城乡/行政/高程/流域梯度及保护区内外 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-004,AUDIT-022 |
| `stats.scenario_compare` 跨时空与情景比较 | YES | YES/受限 | YES/通用记录 | NO | COMPONENT — 固定结果比较 | PASS | PARTIAL | AUDIT-004,AUDIT-022 |
| `stats.sensitivity` 参数/权重敏感性 | YES | YES/受限 | YES/通用记录 | NO | COMPONENT — 固定结果比较 | PASS | PARTIAL | AUDIT-004,AUDIT-022 |
| `solver.rules` 规则型空间方案 | YES | YES/受限 | YES/通用记录 | NO | COMPONENT | PASS | PARTIAL | AUDIT-012,AUDIT-015 |
| `solver.suitability` 适宜性驱动配置 | YES | YES/受限 | YES/通用记录 | NO | COMPONENT | PASS | PARTIAL | AUDIT-012,AUDIT-015 |
| `solver.lp` 线性规划LP | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.milp` ILP/MILP | YES | NO | NO | NO | COMPONENT | PASS | PARTIAL | AUDIT-012,AUDIT-015 |
| `solver.goal` 目标规划 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.network` 网络优化/设施选址 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.cp_sat` CP-SAT | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.ga` 遗传算法 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.nsga2` NSGA-II | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.moead` MOEA/D | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.pso` 粒子群 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.sa` 模拟退火 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.aco` 蚁群 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.gurobi` Gurobi适配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.qubo` QUBO/Ising编码与本地参考 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `solver.quantum` 量子退火/混合求解 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-015 |
| `simulate.urban_ca` 城市/土地利用演变 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.population` 人口增长情景 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.industry` 产业发展情景 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.slr` 海平面/连通静态淹没 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.shallow_water` 浅水动力模型适配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.pollution` 污染扩散模型适配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `simulate.ecosystem` 生态系统演变适配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-003 |
| `runtime.python` Python插件 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-010 |
| `runtime.r` R脚本/包 | YES | YES/受限 | YES/通用记录 | YES/受限 | NO — 当前目录为空 | BLOCKED | BLOCKED | AUDIT-010,AUDIT-011 |
| `runtime.cli` C/C++/Java等CLI | YES | YES/受限 | YES/通用记录 | YES/受限 | NO — 当前目录为空 | BLOCKED | BLOCKED | AUDIT-010,AUDIT-011 |
| `runtime.oci` OCI镜像 | YES | YES/受限 | YES/通用记录 | YES/受限 | NO — 当前目录为空 | BLOCKED | BLOCKED | AUDIT-010,AUDIT-011 |
| `runtime.rest` REST服务 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-010 |
| `runtime.hpc` 远程HPC | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-010 |
| `runtime.bmi` BMI时步接口 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-010 |
| `runtime.arcgis` ArcGIS可选适配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-010 |
| `research.geometric_algebra` 几何代数接口与对照 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-007 |
| `research.hypergraph` 对象—数据—模型超图匹配 | NO（当前可达实现） | NO | NO | NO | NO | NOT_RUN | MISSING | AUDIT-007 |

## 专项平台与Planning对象

| 能力 | 状态 | 问题 | 证据边界 |
|---|---|---|---|
| 研究内容/任务关系 | MISSING | AUDIT-002 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 模型上传—验证—发布 | MISSING | AUDIT-010 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 多模型耦合/Adapter路径/Workflow | MISSING | AUDIT-007 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| PlanningProblemCompiler | MISSING | AUDIT-012 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 独立Objective/Constraint/Decision版本 | VERIFIED | AUDIT-015 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 原生规划单元准备与实际矢量成果 | VERIFIED | AUDIT-015 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| Diagnosis/Candidate/Reassessment | MISSING | AUDIT-013 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 完整RunManifest/ProvenanceGraph | PARTIAL | AUDIT-016 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 固定配置复现 | MISSING | AUDIT-017 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 统一FSM/SSE | PARTIAL | AUDIT-020 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| checkpoint/remote_unknown | MISSING | AUDIT-021 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 通用用户脚本沙箱发布 | PARTIAL | AUDIT-009,AUDIT-010 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| FeatureRevision/EditLease | MISSING | AUDIT-023 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| U0—U3不确定性 | MISSING | AUDIT-022 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 模块Copilot/AIAction | MISSING | AUDIT-033 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 数据库RLS | MISSING | AUDIT-027 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 完整科研报告和图件模板 | MISSING | AUDIT-032 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |
| 成果服务发布 | MISSING | AUDIT-032 | VERIFIED仅本轮规划版本/单元链；其余见相应问题源码及接口边界 |

## 主要动作

| 动作 | 状态 | 实际范围 |
|---|---|---|
| 创建/打开/刷新任务 | WORKING | 四类型持久化，未代表四链可跑 |
| 创建/编辑/搜索/回收恢复项目账号 | WORKING | 管理浏览器链；账号与成员分离 |
| 方法保存/发布/批准/应用/克隆/导入 | WORKING | 实际persisted method-flow；仍有内置指标入口偏航 |
| 从内置指标添加与计算NDVI | WORKING | 真实202/worker/map/原值/hash |
| 六光谱单项产物旧下载 | BROKEN | 真实500，不影响新主下载 |
| Coupler核对匹配 | WRONG_FLOW | 实际执行任务preflight |
| 方法从指标库选择 | WRONG_FLOW | 读取项目已批准定义，不是系统recipes |
| 取消运行 | WORKING | 运行中布尔请求、worker确认；不满足新FSM合同 |
| 分级/时空/模拟/比较缺步骤 | PLACEHOLDER | 明确未接通，不能当可用入口 |
| ModelOps上传→发布 | DEAD_END | 无可操作入口；工程未实现 |
| Planning预检→求解 | DEAD_END | 明确PLANNING_COMPILER_NOT_READY |
| 导入部分成功时错误提示 | WRONG_ERROR | 实际绑定成功，字段loc被generic错误丢弃 |
| 重试导入/并发绑定恢复 | WORKING | 从已受管资产恢复，不重传主件 |
| 主成果/完整包下载 | WORKING | NDVI/规划单元；所有格式bundle未全测 |

## 原145验收索引的本轮处置

这是完整索引，不是宣称执行了145项。取消的旧兼容约束不计PASS；下列仍以最新V3语义解释。NOT_RUN可含相关组件证据，但缺原条完整场景。

| ID | 场景 | 本轮状态 | 说明 |
|---|---|---|---|
| UI-01 | 完整中文导航 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-02 | 统一MapHost | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-03 | Dock拖动 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-04 | 短工具栏 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-05 | 三种状态分开 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-06 | 一次导入 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-07 | 批量加入 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-08 | 八步非重复表单 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-09 | 正常空状态 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-10 | 失效状态 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-11 | 模块职责 | FAIL | Coupler任务预检替代领域匹配、方法指标选择仍为已批准定义。 |
| UI-12 | 目录查询 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-13 | 地图图例 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| UI-14 | 键盘和错误 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-01 | 混合导入 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-02 | 完整GeoTIFF | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-03 | TIFF成组 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-04 | 孤立附件有主件 | PASS | 限定工程夹具及该条动作；不扩展到全业务。 |
| DATA-05 | 孤立附件无主件 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-06 | 定位冲突 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-07 | VAT业务包 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-08 | 多个同名 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-09 | qs分组 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-10 | 解释后补 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-11 | 多图层容器 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-12 | 半批失败 | NOT_RUN | 实测半批成功/失败隔离通过；该条要求的失败项更正后重试未完整重跑。 |
| DATA-13 | 中断与关闭 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-14 | 重试幂等 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-15 | 目录范围 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-16 | 目标上下文 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-17 | 原件快照 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| DATA-18 | 输入需求OR | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-01 | 半像元错位 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-02 | 旋转/剪切 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-03 | 合法零和负值 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-04 | 单位维度 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-05 | 源单位与目标 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-06 | 类别/总量/密度 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-07 | 地理显示与分析 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-08 | 三个域 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-09 | 垂向/非结构网格 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-10 | 时间支撑 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-11 | CF日历 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-12 | COG链 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| GEO-13 | 跨日期线 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-01 | 宽长不统一 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-02 | 方言与编码 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-03 | 年鉴口径 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-04 | 合计和重复 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-05 | 行政边界 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-06 | 总量基准 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-07 | 零与无数据 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-08 | 部分海岸域 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-09 | 回归分割 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| TAB-10 | 分产业 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-01 | 指标目录逐项 | FAIL | 62项内置定义仅8项published；177范围未全实现。 |
| ALG-02 | NDVI基准 | PASS | 限定工程夹具及该条动作；不扩展到全业务。 |
| ALG-03 | 缺NIR | PASS | 限定工程夹具及该条动作；不扩展到全业务。 |
| ALG-04 | 扩张速度 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-05 | 土地强度与类别 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-06 | 评分与颜色 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-07 | AHP手算 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-08 | Entropy/CRITIC退化 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-09 | PCA输出类型 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-10 | 评价PP与PPCI | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-11 | WLC基准 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-12 | WLC缺层 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-13 | 非WLC | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-14 | 全图与块 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-15 | 分级边界 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| ALG-16 | 共同断点 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-01 | 空草稿 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-02 | 部分编辑 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-03 | 不完整发布 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-04 | 条件控件 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-05 | 真实发布使用 | PASS | 限定工程夹具及该条动作；不扩展到全业务。 |
| METHOD-06 | 无权限批准 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-07 | 旧版保护 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-08 | 方法文件导入 | NOT_RUN | 本轮真实浏览器仅CSV方法导入；JSON/YAML、公式安全整条未全跑。 |
| METHOD-09 | 无数据发布模板 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| METHOD-10 | 目标切换 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-01 | 新Python包 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| MODEL-02 | 新R包 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| MODEL-03 | 上传不执行 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-04 | 拆分等价 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| MODEL-05 | 契约失败 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-06 | 真实外部协议 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-07 | 训练预测 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-08 | 环境资格 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-09 | 隔离边界 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| MODEL-10 | ArcGIS适配 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| COUPLE-01 | 硬门禁先行 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| COUPLE-02 | AND-OR替代 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| COUPLE-03 | CSV到density | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-04 | n元超边 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-05 | 无界循环 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-06 | 反事实来源 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| COUPLE-07 | 动态守恒 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-08 | 未收敛 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-09 | 时间与mesh | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-10 | checkpoint恢复 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-11 | 3D约束 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| COUPLE-12 | 几何代数与消融 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| PLAN-01 | PlanningProblem类型 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| PLAN-02 | 缺成本/政策 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-03 | 小MILP基准 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-04 | 无可行/无界/时限 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-05 | 硬约束独立检查 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-06 | true multiobjective | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-07 | 场景固定 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| PLAN-08 | 反事实再评价 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| PLAN-09 | 任务结果引用 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-10 | QUBO本地 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-11 | 量子/商业远端 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| PLAN-12 | 规划发布 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| RESULT-01 | 原生点查 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-02 | 面积转移基准 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-03 | 非等积面积 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-04 | 历史一致性 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-05 | 统计范围 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-06 | 空间结果分支 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-07 | 报告facts | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| RESULT-08 | 图件格式 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-09 | 可比性 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| RESULT-10 | 服务发布 | BLOCKED | 当前工程缺项；不是外部科学阻塞。 |
| AUTH-01 | 项目隔离 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-02 | 角色拒绝 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-03 | DB连接隔离 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-04 | 最后负责人 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-05 | 任务与项目状态 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-06 | 来源三层 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-07 | 撤权与缓存 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-08 | 密码与密钥 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-09 | AI外发与注入 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| AUTH-10 | 审计与回收 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-01 | Schema与迁移 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-02 | 草稿乐观并发 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-03 | 同意图提交 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-04 | outbox可靠性 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-05 | worker租约 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-06 | 取消状态 | NOT_RUN | 实测空间worker运行中取消通过；训练/模拟/远端重试场景未跑。 |
| OPS-07 | 大文件与全域 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-08 | 恶意数据包 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-09 | 同构建回归 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |
| OPS-10 | 干净交付 | NOT_RUN | 本轮非该条完整验收重跑；相关源码/组件/探针见覆盖矩阵，不继承旧PASS。 |

字段/证据索引及探针失败更正详见 [机器清单](COASTMAS-V3-FINDINGS.json)。没有测试的维度不转换为PASS。
