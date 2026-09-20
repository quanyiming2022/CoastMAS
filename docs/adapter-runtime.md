# 模型运行适配器

所有适配器遵循 prepare / validate / execute / collect / cleanup，使用注册版本与可信维护者配置。运行目录独立，执行状态和错误不能由说明文字改变。

| 适配器 | 当前实际行为 | 边界 |
|---|---|---|
| PythonFunctionAdapter | 私有受信回调、独立 Python 进程、有限时间和输出、进程组终止、安全失败诊断 | 不接受用户 Python/pickle 执行；本地进程尚无独立硬内存限额 |
| CLIAdapter | 固定可执行路径与参数数组、无 shell 拼接、超时/取消/输出限额 | 只接受维护者注册命令 |
| DockerAdapter | 固定镜像摘要，先 create 后 start，无网络、只读根与请求挂载，CPU/内存/PID 限制，清理本次自有容器 | Docker 仅属于可信 worker；不会挂载给 API/模型。创建状态不确定时不开始模型 |
| HTTPAdapter | 子进程内 DNS 解析后固定实际连接 IP，HTTPS 验证原主机，拒绝跳转/代理，显式内网授权，输入/输出预算 | 不接受用户地址；不盲重试。超时/取消只停止本地等待，远端完成状态 UNKNOWN |
| RasterGISAdapter | 单位感知计算、分区、缓冲、相交、叠加、重投影/重采样、多边形化 | 无效几何/缺单位/不完整总量覆盖显式失败 |
| MLAdapter | 随机森林分类/回归、固定种子与显式分组划分、签名 joblib 载入、特征顺序复核 | Feature importance 不是因果证据；任意上传 joblib 不执行 |

真实测试在 tests/unit/test_adapters.py、test_gis_adapter.py、test_ml_adapter.py，以及 tests/integration/test_http_adapter.py、test_docker_adapter.py、test_worker.py。HTTP 本地协议测试不是对外部真实科学模型或 LLM 的认证。

运行协议不等于完整部署与 UI 验收。尚需完成应用侧模型注册表与每类适配器的完整用户流程，以及更多异常分支与资源恢复验证。
