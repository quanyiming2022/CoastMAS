# 能力状态

状态定义：REGISTERED=仅登记；IMPLEMENTED=代码存在；EXECUTABLE=可真实执行；VERIFIED=已在注明范围实测；BLOCKED=受具体条件阻塞；NOT_RUN=未验证。不得由菜单或注册推导实现/执行。

| 能力 | 状态 | 范围/证据 |
|---|---|---|
| V3 十个一级中心及权限过滤 | VERIFIED | 四类任务入口和导航浏览器测试；开发中子项不计为可执行 |
| 62 项内置指标定义 | REGISTERED | 8 项有实现，54 项未安装；不宣称 62 项可算 |
| 8 项内置指标核函数 | VERIFIED | next/tests/test_indicator_kernels.py 与当前后端日志；不是完整 A—J 产品验收 |
| NDVI 上传、自动波段匹配、计算、点查与下载 | VERIFIED | 当前工程夹具运行摘要；地图截图存在待修问题 |
| 规划目标/约束/决策独立版本与显式应用 | VERIFIED | planning-objects 浏览器链与后端 tests；不等于规划编译完成 |
| 完整矢量规划单元与面积/重叠检查 | VERIFIED | 后端实际数值/API测试；本次地图视图恢复链失败 |
| 二元 MILP、18 单元内完整 Pareto 求解核 | VERIFIED | numerical/reproduce.py 和 test_planning_solver.py；尚未接入业务队列 |
| 矢量视图保存/恢复 | IMPLEMENTED | 当前浏览器回归失败，不能维持 VERIFIED |
| 规划求解—候选—再评价—比较—报告 | NOT_RUN | 尚未完整实现，不能用独立求解器代替 |
| 完整 ModelOps/Coupler/沙箱/SSE/复现/空间并发/不确定性 | NOT_RUN | 有部分既有模块，但新增平台专项验收未完成 |
| 145 项主验收、177 项能力目录的完整业务证明 | NOT_RUN | 保留 next/acceptance-master.json 逐项索引；不继承旧版 PASS |
| 真实业务科学解释与正式发布 | BLOCKED | 具体科学资料待确认，见已知问题；不作为工程未实现的理由 |

本表是本次提交的最小监督摘要；详细契约与实现直接审查 Git 代码。验收状态与能力状态不是同一枚举。
