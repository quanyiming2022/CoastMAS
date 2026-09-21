# 中国典型海岸真实影像演示

这组演示补充原有海岸筛查、评价与优化功能；不把光谱指数当作海平面模拟、经济观测或经验证的土地覆盖分类。原有合成金标准保留在自动化测试中。

| 场景 | 实际影像 | 计算与范围 |
|---|---|---|
| 黄河口 | S2B_T50SPG_20250925T030120_L2A，2025-09-25 | NDVI=(近红外−红光)/(近红外+红光)，原生10米局部网格 |
| 胶州湾 | S2C_T50SQF_20251027T024827_L2A，2025-10-27 | NDWI=(绿光−近红外)/(绿光+近红外)，原生10米局部网格；不直接阈值分类水体 |
| 长江口 | S2B_T51RUQ_20240901T023727_L2A、S2B_T51RUQ_20250906T023756_L2A | 后期NDVI减前期NDVI；128×128原生10米中心窗口，仅两期共同有效像元 |

## 来源和科学处理

公开数据来源为 [Sentinel-2 COG 开放目录](https://registry.opendata.aws/sentinel-2-l2a-cogs/)，通过 [Earth Search](https://github.com/Element84/earth-search) 查询具体产品。Sentinel 数据使用遵循 [Copernicus 数据条款及其 Sentinel Legal Notice](https://dataspace.copernicus.eu/terms-and-conditions)。显示及分析产物含修改后的 Copernicus Sentinel 数据（2024、2025）。软件许可不替代数据许可。

采集保留完整 STAC 项目、资产地址、波段 scale/offset、实际采集时间、切片网格、每个本地文件的 SHA256。使用 sentinel-2-c1-l2a Collection 1，强制检查资产声明与COG内部scale/offset/NoData一致后才转换；同时保存原始DN数组。物理反射率按每个资产声明的 scale/offset 转换，原始 NoData、非有限值保留为空；SCL 4、5、6 为本示范接受类别，其余遮罩。SCL采用最近邻对齐，不插值类别。产品级云量不冒充局部窗口云量，质量筛选不证明地面真值。

计算再次屏蔽负反射率和小于等于1e-8的分母，NoData不变成零。单期资产时间为精确采集时刻，场景必须同一时刻；不得以一天或一秒的虚构持续时间通过检查。双期观测显式记录两个时间和相同网格，时间间隔不代表连续覆盖。变化不证明因果或长期趋势，潮位、季节和传感器差异仍可能影响解释。

真彩色PNG是显示产品（地理位置由已保存的WGS84边界定义）；它不替代原生反射率GeoTIFF。分析结果保留完整数值矩阵和原始投影网格，同时提供最近邻显示图。NDVI/NDWI固定色标−1至1，ΔNDVI固定色标−2至2；无数据透明，不按每张图重新拉伸数值。

## 界面和复现

在项目“中国典型海岸真实影像演示”中选择场景，查看真实影像、采集日期与来源；可控制图层和透明度、切换双期影像。保存的工作流经统一预检后由独立worker运行，结果中心提供地图、统计、完整JSON和运行清单。执行阶段不调用LLM，不依赖Qwen或云API。

合格采集文件位于 `artifacts/runtime/real-imagery/collection-1`。运行 `.venv/bin/python scripts/prepare_real_imagery.py` 会在首次安装时查询上表四个固定产品并下载局部影像，之后复用通过SHA核验的文件，冲突拒绝覆盖。搜索快照保存在 `artifacts/runtime/real-imagery`。20260921T061111733480Z实测在空快照目录成功查询四个固定Collection 1产品；完整影像下载已有054037882670Z证据。下载需要互联网，不声称离线安装自动具备数据。

完成采集并启动API、worker后运行：

```sh
.venv/bin/python scripts/publish_real_imagery.py --run
```

该入口仅新增固定版本；已有资源与文件不一致时拒绝覆盖。发布调用真实API、等待真实任务结果，失败或超时非零退出，报告保存到 `artifacts/runtime/real-imagery/demo-report.json`。重复执行使用同一幂等请求，不复制运行记录。管理员口令从本地私有配置读取。

## 在线底图

默认不请求在线底图。用户可选 OpenStreetMap 或 NASA GIBS Terra/MODIS 真彩色，并选择NASA日期。版权归属保持可见，网络不可用显示失败，不伪装成已加载。NASA标称250米浏览产品，放大不增加实际分辨率。在线底图只作为背景，不进入分析数据绑定。

遵循 [OSM 瓦片使用政策](https://operations.osmfoundation.org/policies/tiles/)：只加载当前视图，保留浏览器缓存及来源，不批量预取或离线抓取。NASA接口参见 [GIBS官方文档](https://nasa-gibs.github.io/gibs-api-docs/access-basics/)。

## 验证状态

已有证据覆盖校准/无数据、瞬时采集约束、双期网格与日期一致性、图像权限/完整性、旧演示兼容及新种子幂等预检。20260921T054321509734Z证据通过真实发布、独立worker及从原始DN独立逐像元核算；三个结果最大误差均为0、执行LLM调用均为0。20260921T054635635924Z真实浏览器通过三场景影像、双期切换、结果及OSM/NASA在线底图HTTP200；20260921T060227416896Z通过管理员可逆归档及仅显示三个真实场景。机器可读核算见artifacts/research/real-imagery-crosscheck.json。这些是新增演示的验收，不代表CoastMAS全范围验收完成。

## 首轮数据被科学复查否决

旧 sentinel-2-l2a 项目 `9bdf974b-5ad4-5245-a8cd-c9420690f64b` 虽完成了任务执行，但目录scale/offset与COG内部声明不一致，不能作为科学验收通过。黄河口110142个有效红光像元的新旧原始值比较全部恰差1000 DN，确认旧COG已处理偏移而目录仍要求再次扣减。首轮项目已标记异常并可逆归档，三个模型已禁用；原始资源、结果、失败测试与运行日志全部保留。提供方的[同类问题记录](https://github.com/Element84/earth-search/issues/71)支持对legacy集合保持谨慎，但本次修复依据是实际文件与原始像元核查。

新版本改用同日同轨的Collection 1，并以 `scripts/verify_real_imagery.py` 独立从原始DN计算反射率、质量掩膜和指数，对发布结果逐像元检验（绝对误差≤1e-12，包括NoData位置）。任务SUCCEEDED与科学验收PASS是不同结论，不能互相替代。
