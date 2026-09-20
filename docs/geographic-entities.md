# 地理实体与版本查询

地理实体是独立资源，采用 `GeographicEntity` 契约，支持岸段、湿地、地块、行政单元、管理单元、水体、保护区及自定义类型。实体标识与管理单元标识分开；管理单元必须提供后者，不能等于实体标识。结果对象继续由结果中心及不可变结果清单管理，不把地图几何当成结果版本。

源契约保存明确的二维 CRS、几何、属性、版本及带时区的有效时间。岸段使用线，面积实体使用面，自定义支持点、多点、线、多线、面、多面。不接受 NaN/无穷、未闭合或自交多边形、退化几何、三维 CRS、非角度经纬轴或超过 100000 顶点的对象。不能根据数值猜测坐标系，也不自动修复输入几何。有效区间为 `[valid_from, valid_to)`，结束时间可为空。

每次写入在同一数据库事务中追加 `resource_versions` 和 PostGIS `geographic_entities`。空间索引保存转换到 EPSG:4326 的派生几何；原始坐标与 CRS 仍在契约中。转换显式使用 X/Y 顺序，禁止 ballpark 近似，无可用转换即拒绝写入。两个版本表都由数据库触发器禁止更新和删除，编辑必须追加版本，使用预期版本避免覆盖并发更新。

## 使用

登录后打开“地理实体”，输入名称、类型、管理单元标识、源 CRS 和带时区的有效时间，选择单个 GeoJSON Geometry 或 Feature 文件。文件最大 8 MB；不把多实体 FeatureCollection 悄悄合并成一个实体。Feature 属性会随版本保留。未选择新文件的修订保留原几何与属性。读取历史版本后不能用过期版本覆盖当前版本，服务器返回 VERSION_CONFLICT。

页面显示当前空间版本；地图是 WGS84 离线矢量图，不依赖外部底图。实体目录和空间地图每页最多 50 个，目录按名称、地图按标识排序。历史表单不改变“当前空间版本”地图的含义。

## API

- `POST /api/v1/entities`：`project_id` 与 `spec`。
- `GET /api/v1/entities?project_id=...`：分页目录。
- `GET /api/v1/entities/{id}?version=1`：指定不可变版本；省略版本读取当前。
- `PUT /api/v1/entities/{id}`：`expected_version` 与下一版本 `spec`。
- `GET /api/v1/entities/spatial`：项目及 WGS84 west/south/east/north；可加带时区 `at`、`include_history`、`limit`、`offset`。默认只查询当前未归档、启用资源，返回 GeoJSON、`has_more` 和偏移。跨日期变更线的窗口需拆为两个合法窗口，不接受 west >= east。

空间查询和目录读取检查项目权限；所有写请求还需会话 CSRF。空间结果不缓存。历史几何保留各自版本有效区间；版本修订不会自动推断或重写上一版本的结束日期。

## 当前证据与边界

真实 PostGIS 测试会创建独立数据库、执行升级—降级—升级，再验证空间相交、时间筛选、源 CRS 保留、投影转换、不可变触发器、版本冲突及权限。浏览器实际创建、修订、查询旧版本、显示地图并验证过期版本拒绝；证据为 `artifacts/evidence/20260920T130926122354Z-geography-browser.json`，截图在 `artifacts/screenshots/geographic-entities.png`。

当前提供导入和版本修订，尚不能代表整个场景地图工作台、绘图工具及实体关系编辑已经验收。全范围验收和最终覆盖率门槛仍未通过。
