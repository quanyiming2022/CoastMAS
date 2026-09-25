# 已知问题与审计边界

本轮35项：2 P0、26 P1、7 P2，完整位置/根因/证据/依赖见 [问题清单](../docs/audit/COASTMAS-V3-FINDINGS.json)。本轮只诊断，未实施下列整改。

- P0：完整模型上传、沙箱验证与发布链缺失；PlanningProblemCompiler缺失，完整规划提交被阻断。
- P1：一般Coupler页面实际为任务目录预检；方法指标入口仍用批准定义库；Simulation/Comparison与规划候选再评价未完成。
- 真实缺陷：单项产物下载因media_type缺失500；默认422被前端转成无字段提示，预览保存失败恢复不完整。
- 新平台Manifest/Provenance/Reproduce、统一FSM/SSE、checkpoint/remote_unknown、FeatureRevision/EditLease、U0—U3框架未齐备；不能用当前快照、轮询与CAS替代。
- 54项指标未安装；年鉴空间化、完整GIS算子、科研图件/报告/服务发布、AIAction及标准阶段支持有缺项。
- 性能风险：同步时间预检、向量全量读取、全项目多指标重复匹配、大JSON和前端包；容量压力未测。
- 旧透明度偶发失败本轮未复现，最终规划单元恢复链通过，但未声称修复竞态。加载态原图保留，稳定帧已看到真实栅格。
- 原探针定位/时序/错误预期以及第二浏览器硬编码地址均保留并纠正，最终六条测试全在58125。只读核对审计项目不在正式数据库。
- 完整真实业务、恶意代码沙箱/远端/负载、全站逐控件和30层压力未运行；未跑不填PASS。科学定义或定位未知不猜填，工程缺项不转为等用户。
- 原始data_quan、模型包、私有声明、密码、数据库、trace不上传；现有58013/58012不替换。

[整改Wave 0—5](../docs/audit/COASTMAS-V3-REMEDIATION-PLAN.md)仅为下一轮执行依据，本轮到此停止。历史失败和纳管记录保留在before commit及原证据目录。
