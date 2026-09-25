# Web 工作空间运行与验证

当前入口 `http://127.0.0.1:58000`。管理员凭证位于项目私有 `artifacts/runtime/demo-access.json`，不在本文件或 Git 中。初始化不会重置已有密码或覆盖已修改目录版本。

## 一键启动（本机已安装环境）

在 Finder 中双击项目根目录的 `start-coastmas.command`，或在终端执行：

```sh
/Users/quanyiming/projects/CoastMAS/start-coastmas.command
```

脚本自动定位项目，复用同一项目已有的 API、worker、beat，仅启动缺失进程；数据库、Redis 和对象存储使用现有容器与卷，等待健康后启动应用。成功显示 `http://127.0.0.1:58000`，服务在后台运行，关闭启动窗口不会主动停止它们。重复执行不会重置账号、重建数据、重新播种演示或停止已有计算；它也不会强制重启旧服务加载代码更新。

使用前打开 Docker Desktop。需要本项目已安装的 `.venv`、私有 `.env`、已有数据库初始化及前端 `apps/web/dist`。缺少环境或构建会明确报错，不自动安装依赖或更改科学数据。当前基础设施使用本机已有 MinIO 镜像和数据卷，因此本脚本不是全新电脑的一键安装器。

日志与进程编号位于 `artifacts/runtime/start-local/`（私有目录），包括 `infrastructure.log`、`api.log`、`worker.log`、`beat.log` 和 `services.json`。检查网页与依赖就绪、服务进程存活不等于已完成一次科研计算验收。异常后已启动服务保留，修复原因后可再次执行；不手动按旧 PID 结束不明进程。58000 被无法确认的程序占用、发现重复服务或另一次启动正在执行时，脚本拒绝继续并说明原因。

## 手动启动／首次准备

先启动 `docker compose -f docker-compose.infra.yml up -d`，准备 `.env` 的数据库、对象存储和管理员配置，再运行：

```sh
.venv/bin/python -m coastmas init
npm --prefix apps/web ci
npm --prefix apps/web run build
.venv/bin/python -m coastmas api
# 独立终端运行：
.venv/bin/python -m coastmas worker
.venv/bin/python -m coastmas beat
```

前端开发使用 `npm --prefix apps/web run dev`，开发代理指向本地 API 58000。生产静态文件由 API 同源提供，未知 API 路径不会回退为 HTML；缺少构建会返回 503。完整容器部署尚未交付，此处不作为 Docker 验收通过证据。

登录后默认项目为“中国典型海岸真实影像演示”，可查看黄河口、胶州湾、长江口的公开影像、固定版本工作流、地图结果及完整溯源。双期场景可以切换采集日期；在线底图由用户选择OSM或NASA。具体科学处理与限制见[真实影像演示](real-imagery-demos.md)。

原合成金标准项目已可逆归档，自动化测试继续在独立环境中使用它们的夹具。合成海岸筛查金标准为80000 m²、320人；人口采用管理单元均匀分布假设，不能冒充精细人口分布或水动力模拟。管理员功能见[账号与测试环境](admin-and-testing.md)。科研页面已提供冻结目录的A/B/C提交、真实任务状态与报告，完整实验验收状态见[科研评估](research-evaluation.md)。

## 类型与浏览器检查

Python 契约由 `scripts/export_contracts.py` 输出 JSON Schema/OpenAPI，前端通过 `apps/web/scripts/generate-types.mjs` 生成声明，AJV 在运行时检查完整科学对象；API 包装及错误结构另用 Zod 校验。`--check` 检查漂移而不改写。

```sh
.venv/bin/python scripts/export_contracts.py --check
node apps/web/scripts/generate-types.mjs --check
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
.venv/bin/python scripts/e2e.py
```

普通E2E使用真实API、PostgreSQL、Redis、S3和独立worker，由scripts/e2e.py创建随机隔离资源与私有账号，结束后只清理本次测试资源，不往用户演示项目写测试记录。日志与失败浏览器trace保留在忽略提交的artifacts/runtime目录，可能含会话数据。证据由scripts/evidence.py脱敏记录退出码及源码摘要。真实影像现场验收另用acceptance.config.ts。

本轮前端47项通过，完整隔离浏览器19条通过；最新证据按STATE.md更新。前端保留地图/图表包体警告，不修改阈值掩盖问题。上述检查不等于全范围产品验收。

## 地图构建说明

MapLibre 6 使用独立 ESM worker。必须通过 Vite 的 `?worker&url` 打包完整依赖并设置 worker URL；只复制主文件会出现界面控件可见但图形不加载。依据：[MapLibre 官方安装说明](https://maplibre.org/maplibre-gl-js/docs/)、[v6 迁移说明](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/)。地图绘制经纬度校验后的实际GeoJSON、具有来源与WGS84边界的影像显示产品；不从投影坐标猜测位置。OSM/NASA底图按需联网加载，网络失败显式显示。

图表使用实际结果字段，按需注册 ECharts 图表、组件和 SVG 渲染器，参考[官方按需导入说明](https://echarts.apache.org/handbook/en/basics/import/)。模型科学限制及未知面积不因可视化而省略。

会话失效后的受保护请求返回 401 时，前端清除私有查询缓存并重新认证；重新登录也会清除旧账号的项目缓存。服务端权限仍是唯一授权依据。
