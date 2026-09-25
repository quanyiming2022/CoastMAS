# 当前基线验收

本次任务：将现有开发代码纳入指定 GitHub 仓库，并建立持续提交与最小监督证据规则。
目标：`quanyiming2022/CoastMAS` 的 `main`。本地 before：`88f7b629c1bde2c91090e2ff1a47917567895b38`。
当前运行构建：`master-v3-dev25`，58013 开发环境。首次提交收录此前累积工作，不伪造过去逐任务提交历史。
最终 after 与推送状态以实际 Git commit/远程引用和交付消息为准，避免在提交内自引用 SHA。

| 验收项 | 状态 | 实际证据与边界 |
|---|---|---|
| 当前后端测试集合 | PASS | [后端日志](evidence/runs/backend.log)：290 项通过；仅 next/tests |
| 当前前端组件测试 | PASS | [前端日志](evidence/runs/frontend.log)：72 项通过 |
| 前端 lint | PASS | [lint 日志](evidence/runs/lint.log) |
| 类型检查和前端构建 | PASS | [构建日志](evidence/runs/build.log)；仍有大包警告 |
| 实际浏览器：导航、NDVI 操作/数值、Dock、规划配置版本 | PASS | [浏览器日志](evidence/runs/browser.log)：四条链通过，不代表全站/地图视觉全部通过 |
| 规划单元视图保存/恢复全链 | FAIL | 同一日志：预期 opacity=0.6，读取为 1；后续恢复断言未执行 |
| NDVI 成果地图视觉 | FAIL | [1440×900](evidence/screenshots/indicator-result-1440.png)、[1366×768](evidence/screenshots/indicator-result-1366.png)：捕获时未见有效栅格着色，需查明渲染/时序原因 |
| 规划矢量实际地图截图 | PASS | [1440×900](evidence/screenshots/planning-units-1440.png)、[1366×768](evidence/screenshots/planning-units-1366.png)：实际两个工程夹具多边形；不包含保存恢复通过声明 |
| 小型数值可重复性 | PASS | [可重跑脚本](evidence/numerical/reproduce.py)、[实际输出](evidence/numerical/results.json)：NDVI/MILP/Pareto |
| 真实处理节点与结果摘要 | PASS | [NDVI 运行](evidence/runs/ndvi-run-summary.json)：固定输入/算法、原生像元、下载文件哈希；明确工程夹具 |
| 完整新 RunManifest / Workflow / Reproduce 平台要求 | NOT_RUN | 上述摘要只证明现有处理节点，不替代完整平台契约验收 |
| Planning 五条正式端到端业务 | NOT_RUN | 单元准备、配置和独立求解器不等于编译—求解—再评价闭环 |
| 原版应用、tests_v1 和全部历史浏览器套件 | NOT_RUN | 本次未重跑；tests_v1 缺 v1 实现，不能算当前 290 项的一部分 |
| 真实业务科学结论 | BLOCKED | 未获确认的指标含义/方向、A/B/C、TN 定位等只阻断相关正式分析；工程缺项另列 |

[执行命令与退出码](evidence/runs/checks.json)。截图来自当前实际浏览器，已经查看；不更新视觉快照掩盖失败。
GitHub 网络推送在代码提交之后执行，不以本报告代替远程 SHA 核对。
