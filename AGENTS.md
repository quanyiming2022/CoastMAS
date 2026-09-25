# CoastMAS：研发执行约定

## 依据与边界
- 功能与科研范围见 `docs/requirements.md`；读取定位见 `docs/requirements-index.md`。
- 执行与验收补充见 `docs/execution-quality.md`。它只在明确列出的事项上覆盖原任务书，不删除原有必选功能。
- 本项目一次委托、连续研发、统一交付。内部可分解任务、测试、修复和提交，不等待例行“下一阶段”确认；安全授权不能绕过。
- CoastMAS 独立运行；不得读取无关项目、修改或复制 GeoAI 源码。GeoAI 只做可选、授权的 API 对接。

- UI与导航的共享约定见 `docs/ui-guidelines.md`。

## 少重复，不减质量
- 初次按章节理解完整要求并记录需求索引；之后只读取相关文件、符号、差异及失败日志，未知上下文必须补读。
- 默认一个主执行者。确有独立任务时最多增加两个非递归子代理；不要让多个代理重复审计全仓或同时改同一接口。
- 不反复生成规划和长篇汇报；维护简短 `docs/STATE.md` 与需求追踪表。日志写文件，返回退出码、摘要和证据路径。
- 先稳定 ModelSpec/SceneSpec/WorkflowSpec/BindingPlan/Manifest 契约，再连接模块；局部修改，避免无依据重写。
- 默认模块化单体 API＋独立 worker；复用成熟库，不为“通用化”增加微服务或多套数据真源。

## 开发与验证
- 重要逻辑及修复先写可复现测试；实现后立即跑受影响测试。最后在交付代码上跑完整质量门禁、真实后端 E2E、部署验收。
- 强类型、显式错误、服务端权限、数据库约束、任务幂等和不可变结果版本是必选项。
- 不压缩变量名、删除必要注释、跳过测试、放宽断言或屏蔽错误来节省 token。
- 规则可完成的业务不调用 LLM；LLM 仅生成受约束候选，不能绕过数据、单位、基准和权限检查。
- 核心必选链路不得是空实现；抽象协议、明确不支持和未接入外部模型按真实能力标注。
- 禁止伪造模型、运行结果、测试证据或 token 数量；敏感数据和密钥不得进入提示词或提交记录。

## 收尾
- 保护既有用户修改；不得为制造干净 Git 状态执行破坏性清理。
- 所有完成声明必须对应代码、命令、退出码和产物；必选项阻塞就记录 BLOCKED，不能计为 PASS。
- 平台中断不等于项目完成。保存已完成内容、失败原因、未验证项及最小恢复入口，不宣称后台仍在继续。

## GitHub 提交与最小监督证据
- 用户指定仓库 `https://github.com/quanyiming2022/CoastMAS.git`，目标分支 `main`；后续显式指定优先。每个完成任务独立、清晰提交，并普通 push；禁止 force push、amend/rebase 已用于审查的提交历史。
- 开始记录 before commit；结束核对远程分支 SHA 等于 after commit，再提供二者。推送失败如实报告，不把本地 commit 当作 GitHub 已同步。
- 维护 `.review/acceptance-report.md`（仅 PASS/FAIL/BLOCKED/NOT_RUN，PASS 必须引用实际证据）、`capability-status.md`（REGISTERED/IMPLEMENTED/EXECUTABLE/VERIFIED/BLOCKED/NOT_RUN）与 `known-issues.md`。
- 最小证据保存到 `.review/evidence/{screenshots,numerical,runs}/`：实际桌面截图、可重复小型数值、重大流程的真实运行/Workflow/ResultManifest 摘要；缺项和失败不得隐藏，证据必须脱敏。
- Git 直接审查代码/API/数据库/路由差异；不再额外生成 changed-files、diff stat、API diff 或 DB diff 报告。原始业务资料、模型原包、凭据、私有配置、数据库与缓存不提交。
