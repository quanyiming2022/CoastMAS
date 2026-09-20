# CoastMAS Implementation Plan

执行方式：主执行者在当前任务连续实施；用户已明确取消例行阶段确认。
目标：全范围独立科研软件，全部必选项有真实验收证据。
依据：requirements.md、execution-quality.md、architecture.md、requirements-traceability.csv。

每个工作单元：具体失败用例 → 测试红灯 → 实现 → 受影响回归 → 证据及状态更新。

- [ ] src/coastmas/core/contracts.py 与 tests/unit/test_contracts.py：完整版本化契约，非法单位/范围/版本/依赖拒绝。导出 JSON Schema 并检测漂移。
- [ ] core/validation.py、binding.py：语义、Pint 单位、PyProj CRS、垂向、空间/时间覆盖、重采样及 NoData；手算金标准和性质测试。
- [ ] domain/assessment.py、screening.py、optimization.py、ml.py 与研究用例：全部示范算法、边界、复现及合成数据真实文件。
- [ ] persistence/ 与 migrations/：PostGIS、权限、版本、图谱、审计、任务、结果、研究对象；临时数据库升降升验证。
- [ ] adapters/、worker/：六种 Adapter、幂等任务、取消/重启/原子发布；真实进程/HTTP/存储/队列集成。
- [ ] planner/、graph/、scene/：受约束规划、绑定、任务预算、缓存权限复核、完整三场景运行。
- [ ] app/、integration/geoai/：任务书 API、服务端授权、上传与 SSRF 防护、可选独立集成客户端。
- [ ] apps/web/：全部要求页面和操作，地图中心场景、可编辑工作流、结果/溯源/评价/协同/科研，组件测试及真实后端 Playwright。
- [ ] scripts/ 与 Makefile：check/test/e2e/research/benchmark/acceptance，保留退出码、环境、代码标识、时刻及产物。
- [ ] docker-compose.yml 与完整文档：启动与迁移验收、最终覆盖率/性能/科学基准/权限竞态复查、统一报告。

集中检查重点：缺失元数据不可默认为正确；撤权后缓存不可读取；取消后迟到结果不可发布；重复幂等键不同输入冲突；退化科学输入不产出伪分级。
