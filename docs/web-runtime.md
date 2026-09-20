# Web 工作空间运行与验证

当前入口 `http://127.0.0.1:58000`。管理员凭证位于项目私有 `artifacts/runtime/demo-access.json`，不在本文件或 Git 中。初始化不会重置已有密码或覆盖已修改目录版本。

## 启动

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

登录后选择项目，打开工作流 `coastal_impact`，选择 `Synthetic coastal inundation screening`，执行科学预检后提交。运行中心显示真实进度，成功结果可下载完整 JSON 并查看来源、地形筛查多边形和分区人口统计。合成例金标准为 80000 m²、320 人；人口按完整管理单元均匀分布，不是精细人口分布或水动力模拟。智能规划页支持完整目标输入、缺失数据、显式数据选择、推荐依据、候选保存和预算账本。其他必选页面、全部编辑与研究功能仍在研发。

## 类型与浏览器检查

Python 契约由 `scripts/export_contracts.py` 输出 JSON Schema/OpenAPI，前端通过 `apps/web/scripts/generate-types.mjs` 生成声明，AJV 在运行时检查完整科学对象；API 包装及错误结构另用 Zod 校验。`--check` 检查漂移而不改写。

```sh
.venv/bin/python scripts/export_contracts.py --check
node apps/web/scripts/generate-types.mjs --check
npm --prefix apps/web test
npm --prefix apps/web run typecheck
npm --prefix apps/web run lint
npm --prefix apps/web run build
npm --prefix apps/web run e2e
```

E2E 使用真实 API、PG、Redis、S3 与独立 worker，读取私有演示凭证；不 mock 后端。浏览器 trace 可含会话或请求数据，仅写入忽略提交的 `artifacts/runtime/playwright`。公开证据由 `scripts/evidence.py` 脱敏收集退出码和源码摘要。公开截图仅包含当前合成示例。

当前11项组件/契约测试、3项真实浏览器测试覆盖已实现纵向链路，不代表全部操作或完整产品验收。前端包体仍存在地图/图表大块警告，相关模块按需加载；未修改阈值掩盖警告。

## 地图构建说明

MapLibre 6 使用独立 ESM worker。必须通过 Vite 的 `?worker&url` 打包完整依赖并设置 worker URL；只复制主文件会出现界面控件可见但图形不加载。依据：[MapLibre 官方安装说明](https://maplibre.org/maplibre-gl-js/docs/)、[v6 迁移说明](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/)。地图仅绘制经纬度校验后的实际 GeoJSON，不从投影坐标猜测位置；未加载外部底图。

图表使用实际结果字段，按需注册 ECharts 图表、组件和 SVG 渲染器，参考[官方按需导入说明](https://echarts.apache.org/handbook/en/basics/import/)。模型科学限制及未知面积不因可视化而省略。

会话失效后的受保护请求返回 401 时，前端清除私有查询缓存并重新认证；重新登录也会清除旧账号的项目缓存。服务端权限仍是唯一授权依据。
