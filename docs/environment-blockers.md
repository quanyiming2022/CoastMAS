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
