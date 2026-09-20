# 来源、校验与新增设计边界

## 用户原文件

原名称：`粘贴的文本 (1).txt`。
本包保留路径：`docs/requirements.md`。
UTF-8 文件字节数：39665；逻辑行数：3518。
SHA-256：`75a692d308d44bae54afbc0256f97b7441f6e492e3bb5be6744f35bae89b4eb8`。

本包 `requirements.md` 与本次用户上传文件逐字节一致。章节索引由原文 1—76 节标题生成。

## 本次新增设计

`AGENTS.md`、`START_HERE.md`、`docs/execution-quality.md` 为针对用户新增“高效率、节省 token、代码质量高”要求提出的研发约束，不是原项目现成能力或行业统一标准。

模块化单体默认、代理数量、调用次数、候选数量、覆盖率门槛和测试命令均为本项目建议/要求，需由 Codex 在真实工程中实现和验收。本文没有证明已经节省任何百分比的 token，也未替用户执行 CoastMAS 研发。

原功能范围不缩减；明确覆盖事项集中在执行规范第 1 节。当前环境或授权不足时，相关必选项不能虚报通过。

## 核对过的官方资料（2026-09-20）

1. OpenAI / ChatGPT Learn，Best practices。用于核对精简持久指导、任务相关上下文、测试与审查的建议。地址：`https://developers.openai.com/codex/learn/best-practices`，访问时重定向至 `https://learn.chatgpt.com/guides/best-practices`。
2. OpenAI / ChatGPT Learn，Custom instructions with AGENTS.md。用于核对项目级指导发现方式；长需求文档不等同于短常驻规则。地址：`https://developers.openai.com/codex/guides/agents-md`，访问时重定向至 `https://learn.chatgpt.com/docs/agent-configuration/agents-md`。
3. OpenAI / ChatGPT Learn，Subagents。用于核对并行独立工作、共享文件冲突和推理强度的取舍。地址：`https://developers.openai.com/codex/subagents`，访问时重定向至 `https://learn.chatgpt.com/docs/agent-configuration/subagents`。
4. OpenAI API，Latency optimization。用于核对减少无必要请求、紧凑输入输出和非 LLM 确定性处理。地址：`https://developers.openai.com/api/docs/guides/latency-optimization`。
5. OpenAI API，Prompt caching。用于核对缓存配置、命中条件和模型差异；不据此承诺特定产品的节省比例。地址：`https://developers.openai.com/api/docs/guides/prompt-caching`。

官方功能和接口可能更新。实施时只在实际用到的参数和能力上检查所选模型/客户端版本，不凭任务文件虚构产品配置。无需为普通局部编辑反复检索上述资料。
