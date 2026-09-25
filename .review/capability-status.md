# 本轮能力状态

只采用最新诊断枚举：VERIFIED、EXECUTABLE_NOT_VERIFIED、PARTIAL、UI_ONLY、API_ONLY、REGISTERED_ONLY、BROKEN、MISSING、BLOCKED、NOT_TESTED。各条按声明范围，不将注册/菜单等同实现。旧纳管记录在before commit保留。

[177项逐项矩阵](../docs/audit/COASTMAS-V3-COVERAGE.md)与[机器清单](../docs/audit/COASTMAS-V3-FINDINGS.json)：PARTIAL 40、MISSING 79、VERIFIED 1、REGISTERED_ONLY 54、BLOCKED 3；不是完成率。另列18项平台补充。

| 能力 | 状态 | 边界 |
|---|---|---|
| NDVI工程输入→自动匹配→实际产物/原生点查/主下载 | VERIFIED | 最终六链及数值证据；旧单项下载另列BROKEN |
| V3导航、四类任务 | PARTIAL | 10中心/54注册/17链接；32步中的17步未接通 |
| 8内置指标核、19类型化算子 | PARTIAL | 核函数数值已测；用户完整配置/执行不全 |
| 其余54内置指标 | REGISTERED_ONLY | 明确未安装，普通任务不可算 |
| 项目/用户管理与规划独立版本 | PARTIAL | 已测CRUD/权限/恢复/412；未称完整V3领域对象齐备 |
| 旧单项产物下载 | BROKEN | 真实500，不影响正确主Artifact路径的独立结论 |
| 方法编辑指标选择 | PARTIAL | 仍指向批准定义库，未与普通内置指标统一 |
| 通用Coupler、完整ModelOps、Planning编译 | MISSING | 指标专用匹配和独立求解核不能替代 |
| 不确定性、Reproduce、FeatureRevision/EditLease | MISSING | 新平台专项未交付 |
| 真实模型上传后全链、恶意沙箱/性能专项 | NOT_TESTED | 入口缺失或本轮未执行，不记PASS |

证据统一见验收报告及机器索引，避免重复实现说明。
