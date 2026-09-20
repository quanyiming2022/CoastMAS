# 环境状态与阻塞记录

## Docker 磁盘：已恢复
2026-09-20 用户完成虚拟磁盘调整，实测 Docker `/dev/vda1` 86.3G、可用 54.4G。原 ENOSPC 是历史故障；没有删除其他项目镜像、容器、卷或构建缓存。

持久 PostGIS（55432）、Redis（56379）、MinIO（59000）均已健康。真实 PostgreSQL 89 项综合测试通过，MinIO 不可变写入/读取校验测试 2 项通过。基础设施健康不代表完整软件部署验收通过。临时内存盘数据库 55433 已停止，后续测试使用持久服务内独立临时数据库，仍只删除测试自行创建的库。

## MinIO 运行时：已恢复服务，稳定性待最终验收
官方 Quay hotfix 摘要 `sha256:cf3dadcfa1fb0324f43958bad1abba986d53c4ecc04d4d50b46c7dcda28bd3cd` 已成功拉取并启动，显式 AMD64 仿真。历史 Docker Hub/tag/架构失败记录保留。

2026-09-20 11:27 UTC 回归中出现签名错误与 Go 运行时 SIGSEGV；容器退出 2，未被 OOM 杀死。完整脱敏日志为 `artifacts/evidence/minio-runtime-crash.log`。仅本项目对象卷已只读备份，摘要记录为 `minio-before-native-backup.json`，备份本体仅保存在忽略提交的私有 runtime 目录。

调查发现可用官方 ARM64 镜像为 2025-09-07 原始版，早于当前 hotfix，未降级替换。保留原镜像重启后 `20260920T114117406584Z-workspace-storage-recovery` 的 17 项真实回归通过。架构仿真是否为根因尚未确认；单次恢复不算稳定性验收。原失败证据 `20260920T112635630804Z-workspace-and-bootstrap` 保留。新增 `/health/live` 与 `/health/ready` 区分进程存活和数据库/对象存储/队列可用性；旧 `/health` 仅检查数据库。

## 外部 LLM：仍未配置
进程环境未配置 OPENAI_API_KEY、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL；没有输出密钥值。真实外部 LLM 对照实验 NOT_RUN/BLOCKED，确定性测试不算外部实验。当前可独立继续开发，不因此等待例行确认。

## 完整交付：尚未通过
尚有前端、工作流执行链、三个完整场景、科研实验与统一验收等未完成项，详见 STATE 和需求追踪表。

2026-09-20 13:30 UTC，原 AMD64 hotfix 再次退出 2，日志为 zstd `invalid tableLog` panic，发生在 MinIO 内部 dataUsageCache/namespace scanner。数据库和 Redis 仍健康。完整回归 `20260920T133027591712Z-knowledge-graph-backend-full` 为 238 passed / 29 errors；浏览器 `20260920T133035539580Z-knowledge-graph-all-browser` 为 2 passed / 3 failed，不能计为完整通过。压缩 panic 与此前 SIGSEGV 是否具有同一根因尚未证实。

对象卷保持停止，已再次只读私有备份（`minio-before-native-source-backup.json`，67616 bytes，SHA256 7e92f6082bdd8ea55ef9fcfd788b1bb0b9f6777ce4ee93afbca60cd3c05c0a40）。官方热修复 ARM64 下载路径返回 410；Docker Hub 的 Go 镜像访问超时，未无限重试。官方 codeload 源码和 Go 工具链下载可达，正在准备固定官方安全版源码的原生 ARM 构建及隔离卷验证，尚未切换或宣称恢复。

同轮实体浏览器失败另有独立前端原因：保存 mutation 等待地图刷新后才重置选中版本，覆盖用户在等待期间选中的历史版本。可控延迟测试 `20260920T133534251873Z-entity-selection-race-red` 已复现；修复把已提交版本选择置于背景刷新之前，全部14项组件测试 `20260920T133636364262Z-entity-selection-race-fixed` 通过。没有放宽版本冲突断言。
