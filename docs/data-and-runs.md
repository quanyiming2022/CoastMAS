# 数据文件与运行接口

上传通过项目权限检查后计算真实 SHA-256，读取实际格式，核对单位、CRS、基准等可检验的登记内容，再写入不可变对象存储和目录版本。上传文件名不参与存储路径。元数据直接登记和更新将 validated 设为 false，不能绕过实际校验。重新验证追加版本，保留旧版本。

支持 GeoTIFF、COG、GeoJSON、Shapefile ZIP、单层 GeoPackage、CSV、JSON、NetCDF 的结构检查。当前栅格读取单波段，NetCDF 读取明确命名的数值变量；复杂多层选择和全格式工作流 ingestion 尚待实现。文件上限 64 MiB，栅格/NetCDF 上限 400 万值，CSV/矢量上限 10 万记录。Shapefile 压缩包限制 32 个条目及总解压大小，验证路径、配套文件和 CRC，不提取任意目录。预览仅前 10 行/要素或小型 JSON。

原生解析在独立 Python 子进程内执行，30 秒期限、4 MiB 输出上限。进程会话隔离和取消沿用运行适配器；当前本地 Python 并无独立硬内存限额，生产资源限制仍需部署验证。NetCDF 不在 API 的多个线程内并行读写，其底层库的线程限制见 [官方说明](https://unidata.github.io/netcdf4-python/)。矢量内存文件和驱动限制依据 [Fiona API](https://fiona.readthedocs.io/en/stable/fiona.html)。

目录质量标记的 scope 是 structure_and_declared_metadata。它证明文件结构和可验证元数据通过检查，不证明观测准确。CSV 与矢量属性的单位来源是用户声明；GeoTIFF 和 NetCDF 的单位会与文件实际值对照。无限值不能伪装成 NoData。

工作流运行请求只指定工作流/场景版本和随机种子。服务端读取授权资源，检查启用状态、科学约束和已注册运行时，构造 RunManifest 后持久提交 QUEUED。独立 dispatcher 从数据库取待执行任务，不依赖 HTTP 请求中成功发布队列消息。

Idempotency-Key 按项目与用户隔离；事务级锁使并发相同请求共享同一快照时间和任务。不同科学输入复用键返回冲突。取消与发布使用事务检查；失败/取消后的显式重试创建新任务并记录 RETRY 来源。远端状态未知时拒绝重试，需先解决远端状态。

结果元数据、内容和追溯每次都重新检查当前权限。下载读取实际对象并核对大小与 SHA-256，不将储存地址当作成功证据。追溯读取并校验不可变任务快照。结果发布、用户复核、公开发布是不同状态，完整 Result Center 页面尚未交付。

当前证据：`artifacts/evidence/20260920T092439870312Z-catalog-runs-full.json`，172 项现有测试通过，包括真实数据库、队列、对象存储、子进程和受控容器。完整三场景 UI E2E 与产品验收尚未通过。
