# 外部数据源与文件快照

数据目录 → 外部数据源 → 登记数据源。选择管理员批准的连接器，填写输出文件的来源、许可证、变量、单位、坐标及时间声明。登记本身不表示已有数据或验证通过；导入实际读取目标，检查内容后保存项目内的不可变文件快照。

## 管理员配置

设置 COASTMAS_DATA_SOURCES_CONFIG 为本地 JSON 文件的绝对路径，并将权限设为 0600；重启 API 加载。未配置时目录为空，应用其他功能仍可运行。配置文件采用“连接器标识 → 配置对象”的映射。每项包含 name、revision（正整数）、projects（明确的项目 ID 列表）和 kind。修改连接器目标或查询定义时提高 revision。密钥只通过环境变量或本地 .env 引用，不能写进登记表单、公开文档或提交记录。

HTTP 配置：kind=http，url 为固定目标，allow_private 默认为 false。headers_env 可把 Authorization 或 X-API-Key 映射到环境变量名；变量值是完整请求头值。公共地址要求 HTTPS。内网服务必须显式 allow_private=true。连接时固定解析出的 IP，禁止重定向、代理转发和压缩传输，不接受用户临时传入任意 URL。

PostgreSQL 配置：kind=postgresql，dsn_env 指向 postgresql+psycopg 连接字符串的环境变量名，schema/table/columns/order_by 明确批准的表和列。建议数据库账号仅有这些对象的 SELECT 权限，按部署环境配置 TLS。导出采用只读事务、5 秒语句超时、UTC 会话时区和有序 CSV。排序键必须唯一且非空；不提供任意 SQL 输入。

连接器最多读取 64 MiB 或 100000 行，整体进程期限不超过 30 秒。数据库超大字段在传输前测量并拒绝；用户函数尝试写库也被只读事务拒绝。文件解析另有隔离进程和资源边界。

## 版本与来源

每次导入固定数据源版本及连接器配置版本，并存储实际字节 SHA-256、读取时间和质量记录。相同导入键返回同一个数据快照，不重复读取服务；“准备下一次导入”显式建立新键。编辑数据源形成新版本，不改写旧文件。数据库外键记录来源关系，数据工作台链接到精确历史来源；普通可编辑质量字段不能伪造此关系。相同文件的后续质量版本仍可追溯到原导入。被历史快照引用的数据源受归档保护。

## 本地真实验收源

scripts/serve_acceptance_source.py 只监听 127.0.0.1:58090，仅提供 /observations.csv，内容是明确标记的合成高度 0 和 2，不是外部科研观测。当前本地 demo-csv 配置只批准演示项目。该服务用于真实 HTTP → 检查 → S3/数据库 → 浏览器流程；外部生产服务需要用户自己的批准配置，不能将本地合成实验冒充真实外部资料。

## 当前证据

- 20260921T013711682296Z-data-connector-boundaries-green：4 项真实连接器测试通过，覆盖 HTTP 限制、数据库只读、超大字段和时限配置。
- 20260921T014137148181Z-source-registration-green：11 项相关后端通过，含幂等快照、来源历史和依赖保护；78 个源文件类型检查通过。
- 20260921T014457755453Z-source-config-green：8 项配置与连接器/API 测试通过，秘密引用和配置文件权限受检。
- 20260921T015132327639Z-source-lineage-ui-build：前端类型、lint、单元测试和构建通过。真实浏览器验收正在运行，结果尚未计入。

此增量不是全范围交付验收；统一覆盖率、全部研究实验、完整部署与剩余业务页面仍待完成。

- 数据源真实浏览器通过：20260921T015442008877Z-source-catalog-browser，2条（HTTP登记/重复导入同快照/零值/历史来源/修订/归档保护与本地上传共享表单）。PostgreSQL经API到S3实际CSV导入、跨项目连接器拒绝也通过（20260921T015742904951Z-source-postgres-api，9项）；全仓lint、78源文件mypy、契约漂移检查通过。source-catalog-backend-full(session57612)与source-catalog-browser-full(session48728)正在运行，期间不改源码。

- 数据源增量完整回归通过：20260921T015906646890Z-source-catalog-backend-full，304 passed、2 warnings；20260921T015904965192Z-source-catalog-browser-full，15 passed。同一源码SHA 9ba89332db08e47313a0bfe0c3ac08d04006f2f92f2e80b7dc06e6e91129b97b，运行期间无源码变化。覆盖5995/6773行、1603/2230分支（约71.9%），最终分支门槛未达。下一步评价中心指标定义/体系版本管理；§29已定位读取，现有domain/indicator_frames.py和assessment.py复用，不另造算法。外部LLM实验仍缺凭证，其他独立工作继续。
