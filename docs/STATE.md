# CoastMAS 执行状态

- 项目已依用户授权全量迁移到 `/Users/quanyiming/projects/CoastMAS`；原 Documents 目录已移走。始终显式指定工作目录。
- 完整需求和执行规范已读；唯一映射 `requirements-traceability.csv`。全部 76 节与 EQ 有效，尚无完整产品交付。
- 最近已保存提交 `ac3d2b8`（科学算法、数据库、API、worker）；本文件描述其后同批模型目录与匹配改动，最新提交以 git log -1 为准。
- 已实现：版本化契约、DAG/科学预检、单位/CRS/语义/时间/总量守恒；综合评价/熵权/TOPSIS/多期/连通筛查；MILP、AST 栅格计算、分区统计、适宜性；固定种子及分组划分随机森林、HMAC 私有模型存储。
- 已实现：PostgreSQL 用户/项目/成员/不可变版本/审计，幂等任务、租约、心跳、取消/失败确认与原子发布；Argon2 会话、CSRF、FastAPI 模型/数据/场景/工作流版本 API。
- 已实现：受限 Python/CLI 子进程适配器；超时、取消、输出预算、子进程组清理；MinIO 校验与不可变写；GeoTIFF 读写/重投影及元数据验证；文件到绑定的真实数据解析。
- 已实现：锁定注册版本的 DAG 执行器与 Celery worker；真实 Redis → 读取 MinIO → 子进程 → MinIO 结果 → PostgreSQL 发布。重复投递仅执行一次；执行中的取消及撤权停止进程且不发布。
- 已生成所有要求的合成样例（真实 GeoTIFF、GeoJSON、CSV）。三个计算层场景有手算金标准及研究产物；不等于 UI/工作流完整演示验收。人口估计显式采用单元内均匀分布，海平面模型不称水动力模拟。
- 最新统一测试：`20260920T085803263518Z-model-catalog-full`，158 passed，2 项依赖弃用警告。类型/lint `20260920T085743*` 通过。软件包可安装并从 /tmp 导入，pip check 通过。
- 覆盖率：行 88.3029%、分支 66.7544%；业务分支及核心门槛尚未通过。不得宣称完整质量门禁通过。
- 回归：`.venv/bin/python scripts/evidence.py combined -- .venv/bin/python -m pytest -q --cov=coastmas --cov-branch --cov-report=json:artifacts/coverage.json`。
- 计算层演示：`PYTHONPATH=src .venv/bin/python scripts/evidence.py demonstrations -- .venv/bin/python scripts/run_demonstrations.py`。
- Docker 磁盘已由用户调整；持久 PostGIS 55432、Redis 56379、MinIO 59000 均健康。临时内存盘 PostGIS 55433 已停止。测试只创建/降级/删除自身随机临时库与临时 bucket，不清理其他项目。
- 外部 LLM 凭证未配置；真实外部对照仍 BLOCKED。完整部署与完整 E2E 仍 NOT_RUN，参见 environment-blockers.md。
- 证据记录包括源码/测试/迁移/部署/样例内容摘要、git commit、依赖版本与真实退出码，保留失败历史。
- 六类适配器已实际接通：Python/CLI、固定摘要的无网络只读 Docker、固定目标且拒绝重定向的 HTTP、真实 RasterGIS、签名模型与特征顺序约束的 ML。子进程错误保留科学代码与安全调用栈；HTTP 中止保留远端状态未知。
- 已实现投影格网真实相交面积总量守恒分配；覆盖不完整/NoData 拒绝推断未知总量。
- 接下来：运行/任务/结果 API；注册内置模型并把三场景拆解为可规划 DAG；规划/图谱/实体/数据导入；完整 API/UI；协同、动态评价和科研页面；契约生成/全门禁/最终文档与统一验收。
- 特别待解决：存储孤立 attempt 对象的保留清理；worker 中完整保存适配器诊断；显式时间/跨 CRS 保守分配节点；工作流实际数据输出元数据；分支覆盖。当前接口对未实现的转换显式拒绝，不算功能通过。
- 主执行者单独连续推进，没有启动子代理。不得重新全仓规划或重新生成已有能力；按失败/缺口局部修改。
- 当前没有完整前端地址或演示账号。平台中断应从本状态继续，不代表完成，也不声称后台继续执行。

- 覆盖率环境已修正：coverage 7.16.1 的 a1_coverage.pth 在本机带 UF_HIDDEN，Python 会跳过；仅清除了项目 .venv 内此文件的隐藏标记。已用最小子进程证明采集 active=True，python_runner 28/29 行被采集。无业务包排除。
- 提交前发现一份早期数据库失败日志回显本地密码，已在首次提交前脱敏并保留原退出码，私有原日志位于 gitignore 的 artifacts/logs，权限 0600。证据收集器现自动脱敏并拒绝带已配置密钥的命令参数。

- 新增模型静态拆解（不执行上传代码）、安全 JSON/YAML 导入导出、复制、历史、启用/禁用、保护引用的归档。元数据导入不得自证 VALIDATED/EXECUTABLE。真实 API 测试通过；注册运行时审批尚未实现。
- 新增模型检索与两级匹配：硬约束失败无分数，兼容资产逐个检查，排序权重可配置；缺失耗时为 null。生成的是单模型候选片段，不等于多模型场景规划。
- 新增迁移 0004，保存工作流对精确模型/数据版本的不可变引用；并发引用/归档、旧 ORM 版本缓存、撤权缓存和错误被捕获后的事务原子性均有真实数据库回归证据。
