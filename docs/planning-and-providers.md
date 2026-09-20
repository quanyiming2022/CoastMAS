# 结构化规划与提供方

三个确定性模板不依赖外部模型：

- `海岸影响筛查：海平面上升0.5米`，也接受任务书中的完整示例句式。
- `可持续性评价：等权综合评价`，权重可选人工权重、熵权；单期排序可选 TOPSIS。
- `多期变化评价：人工权重综合评价`，跨期使用共享参考界限和权重。

规则匹配整个输入。未知地名、附加条件或混合任务不会通过关键词截取而消失。结构化 ManagementGoal 可以直接提交；多期 TOPSIS 缺少共享理想点定义时拒绝。模板不是通用水动力或任意自然语言求解器。

## 工作流生成

规划器从授权的不可变目录版本选择可信注册组件，生成完整多节点 DAG。没有兼容数据、存在多个兼容数据源、缺少可信模型、场景输出无法满足时，返回 missing_conditions 并使 candidate_workflow 为空。通过 selected_data 显式指定歧义输入的精确数据版本。每个可保存候选都重新经过单位、CRS、基准、时间、尺度、参数及约束预检。人口估计仍遵守科学方法文档中的显式假设。

`POST /api/v1/plans` 接收 project_id、scene 版本引用、goal、可选 selected_data 和 allow_external，要求 CSRF 与 Idempotency-Key。同一幂等键不能更换目标、版本或授权。`parse`、`recommend`、`build-workflow` 三个后续 POST 路径共享同一个 plan ID 和规划产物。`POST /api/v1/plans/{id}/workflow` 保存已验证候选；随后使用工作流 run 接口运行。读取和复用时重新验证当前权限、资源启用状态和科学契约。

## 外部提供方

OpenAICompatibleProvider 实现 LLMProvider，接收管理员配置的 base_url、model 和 SecretStr api_key；由 create_app 的 llm_provider 注入。应用引导和环境配置仍在后续集成范围内，不依赖凭证也可运行三个确定性模板。

使用 Chat Completions 的 JSON Schema 结构化输出和 max_completion_tokens。协议依据：[官方结构化输出说明](https://developers.openai.com/api/docs/guides/structured-outputs)、[官方 Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)。具体兼容服务及模型必须实际支持该协议；不静默降级为自由文本。

输入只包含必要契约摘要、场景条件和数据元数据，不包含源文件地址、栅格内容、原始表格或运行配置中的凭证。首次候选上限 6，可在同一 trace 内扩展到 12；同时报告实际候选总数，截断列表不能声称全局最优。未知目标先保存为 unresolved_goal。调用共享解析/推荐/构图接口时，只有已授权且提供方已配置才会发起请求。

一个 generate 调用只发送一次 HTTP 请求，无 SDK 隐藏重试，无重定向。异常或格式错误不会自动改写为成功。后续显式调用仍使用原 trace，默认总预算 2。数据库行锁负责原子扣减；请求发送前提交预算与发送记录。保守预留在异常退出后不返还，避免不确定状态导致超额请求。

reservations 是已占用额度；dispatched_at 表示开始尝试发送；http_status 非空表示收到 HTTP 响应。网络失败后的远端状态仍可能未知，不能把预留次数伪称为已收到模型响应的次数。记录请求/响应摘要、请求模型、响应报告模型、端点、时间和错误码。提供方没有返回用量时 usage 为 null；缓存 token 仅按实际返回字段保存，不推算费用或缓存命中。终态记录和 trace 输入由数据库触发器保护。

`GET /api/v1/plans/{id}/requests` 返回调用账本，权限限规划拥有者及当前项目访问。提供方只能提出注册模型与版本、数值参数、数据绑定和 DAG；未知模型、重复参数、范围越界或遗漏场景输出均拒绝。自然语言解释仍标为需要审阅，schema 合法不代表科学含义自动正确。

## 真实验证范围

已用真实 PostgreSQL 测试并发预算和撤权；用本地真实 HTTP 服务测试协议、用量记录、截断/拒绝/无效 JSON 及三个接口共享额度；用真实 MinIO 文件与进程执行器测试三个模板计算。规划 API 到保存、运行、持久结果的评价场景链路已验证。

本地协议服务是测试夹具，不是外部 LLM。外部凭证未配置，真实模型质量、供应商兼容性、成本及科研对照仍 BLOCKED。完整界面和统一部署验收仍未完成；应用级计算结果缓存尚未实现，规划产物复用不能冒充计算结果缓存。

## Web 操作与稳定身份

智能规划页已连接真实规划 API：选择场景、输入完整管理目标、查看任务拆解/数据缺口/推荐依据。多个合格数据候选不能静默挑选，需在对应变量选择精确目录版本后重新规划。输入变动后旧产物会标记过期，禁止直接保存。确定性模板不产生外部请求，账本显示预留数与提供方原始用量；未报告用量保持 null。

提供方产物新增共享 `ProviderPlanningArtifact` 契约，必须保留 `interpretation_requires_review=true`，不能把符合 JSON Schema 当作目标解释已经正确。真实外部提供方尚未配置；相关 UI、真实外部研究及人工复核流程仍需后续完整验收。

工作流身份现在对场景、目标、图与最终绑定使用排序键的规范 JSON 摘要。测试已复现并修复“数据库改变对象键顺序导致重复 ID”；字段顺序不影响身份，实际选定数据不同仍产生不同身份。旧工作流/结果/快照不会被重写或删除。此前算法生成的标识仍可读取，新建规划使用稳定算法，目录允许同名不同标识的工作流。
