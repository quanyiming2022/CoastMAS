# 原生对象存储构建与恢复记录

本机是 Apple Silicon。旧 Quay AMD64 MinIO hotfix 两次进程崩溃，分别为 Go SIGSEGV 和压缩扫描路径 `invalid tableLog` panic。失败日志和退出码保留在 evidence；没有把重启或超时当成通过，也没有删除已有结果。

## 当前运行身份

- MinIO 官方源码：`9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`，官方 `RELEASE.2025-10-15T17-29-55Z` 安全版。
- 工具链：Go 1.26.8，官方 macOS ARM64 工具链归档 SHA256 `a012b25b571bd0138a03dcd25375ceba866fe5ca822f426d2c66a4de56fd3f4b`。
- 运行平台：Linux/ARM64，静态编译，scratch 基础镜像，用户 10001:10001。
- 镜像内容 ID：`sha256:072e3ef119f19b6ebee3cb0129309f0ed50ff9988fae2b43ada4a68687334fb2`，基础 compose 按此 ID 使用本地镜像，禁止自动拉取同名替代品。
- 二进制 SHA256：`6b3b2e501e04c41960a170c6c1f37d75e71af87a5b424713f64cc72b5bb7f99f`。
- 当前对象卷：`coastmas_objects_native`，显式 external 卷。原 `coastmas_coastmas_objects` 保留用于调查和回滚，未覆写。PostgreSQL/Redis 的已有镜像也已改为本地核对过的仓库摘要。

官方[安全发布说明](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)说明此版包含会话策略权限修复，并要求社区版从源码构建。这里固定该官方安全源码，没有退回已拉取的 2025-09-07 ARM64 旧二进制。该选择不构成“所有依赖安全问题已审计”的声明；整体安全与部署门禁仍待统一验收。

## 重建入口

```sh
.venv/bin/python scripts/build_minio_native.py
docker build --platform linux/arm64 \
  -t coastmas/minio:9e49d5e-go1.26.8-arm64 \
  -f deploy/minio/Dockerfile artifacts/runtime/minio-native-build/image
```

当前恢复构建脚本明确支持 Apple Silicon macOS 构建主机，输出 Linux/ARM64 镜像。它自动下载固定 SHA 的工具链和源码，每次从已核对归档展开全新源码目录；Go 依赖保留 `go.sum` 与签名校验数据库，使用 `-mod=readonly`，不修改上游代码。工具链与模块缓存位于忽略提交的 runtime，生成镜像附带源码归档和 AGPL 许可证。其他构建主机的工具链及完整一键容器部署还需补齐，不能以本文件代替最终部署验收。

本机 Go 直连官方模块源超时，而同 URL 的 Python TLS 请求成功。构建脚本因此启用仅监听 127.0.0.1 的临时转发器，目标固定为官方 `proxy.golang.org`，有请求并发/大小/超时上限；没有关闭 Go 校验，也未修改全局网络设置。构建结束关闭转发器。首轮转发并发连接失败记录保留，调整接入队列和并发后编译通过。干净源码重建的二进制摘要与首次一致，证据 `20260920T140318755553Z-minio-native-repeatable-build`。

镜像构建元数据可能使重新构建的镜像 ID 不同；部署时必须核对新镜像身份和二进制摘要，再明确更新 compose 的固定 ID，不能伪造 registry manifest digest。当前 ID 对应本机已实际验证的镜像。

## 数据恢复与验证

旧服务停止时进行了只读私有备份：`artifacts/runtime/storage-backup/minio-before-native-source-20260920.tar.gz`。目录 0700、归档 0600，未提交 Git。大小 67616 bytes，SHA256 `7e92f6082bdd8ea55ef9fcfd788b1bb0b9f6777ce4ee93afbca60cd3c05c0a40`。备份恢复到空的新卷，使用独立项目和 59100/59101 端口验证；旧卷不参与新服务写入。

`scripts/verify_storage_copy.py` 对数据库内全部 S3 资产版本和结果描述进行 checksum 检查与实际对象读取。本次 11 个资产版本、7 个既有结果、187363 bytes 全部一致。随后在该次运行独有的测试桶中，以并发 8 验证 200 次写入、3168 次读取、连续健康检查，共 120.197 秒；最后仅删除该次测试桶和其对象。证据 `20260920T135724170625Z-minio-native-storage-verified`。中间验证脚本关联歧义错误保留，修正显式外键后重跑，未跳过任何对象。

验证通过后先停止隔离服务，确保一个卷只有一个写入服务，再切换正式 59000/59001 端口。API `/health/ready` 已恢复 database/object_storage/queue 全部 ready。新旧 MinIO 版本和架构同时变化，因此这只证明当前恢复方案通过所列测试，不能单凭它断言旧崩溃的唯一根因或长期稳定性。

切换后的新增数据只在新卷中；回滚前必须停止写入并备份新卷，不能直接用旧快照覆盖最新状态。普通启动不删除卷、不重置账号，也不运行 `down -v`。完整后端及真实浏览器回归另留 evidence，失败历史永久保留。
