# 科学方法与实现边界

当前文档对应正在开发的核心函数，未表示完整系统已验收。

## 评价
`domain/assessment.py` 接受显式参考上下界与指标方向；超出参考范围、缺失/非有限值、零宽参考拒绝执行，不静默剪裁。常数样本列可在外部非退化参考下计算。权重要求非负且总和为正并归一化。熵权处理 0 log 0 为 0，常数列信息权重为 0，所有列无信息则拒绝生成权重。TOPSIS 使用向量归一化与加权理想点欧氏距离；理想点退化时报错，不生成伪排名。多期使用相同参考和权重，输出竞争排名、末期减初期变化、按实际时间坐标的最小二乘斜率。

## 淹没筛查
`domain/screening.py` 仅是地形连通性筛查，不是二维/三维水动力模型。输入单位为米；绝对水位为显式 baseline + increment；垂向基准缺失或不同阻断。显式海侧种子、4/8 邻接、屏障与 NoData 决定连通域；高度等于水位计为潜在淹没。NaN 为 NoData，输出 -1，绝不当作低风险。面积使用调用方明确提供的平方米像元面积，不能把经纬度平方当平方米。

## 适配
Pint 用于同维单位及偏移温度转换。PyProj 强制 x/y 顺序，禁用 ballpark 并要求可用最佳转换；垂向变换不能从水平 CRS 可转换推断。总量分配矩阵按源面积份额定义，源覆盖列和必须为 1（绝对容差 1e-10），输出总量容差相对/绝对 1e-10。未获批准语义映射不自动接受。时间插值不外推，积累量只能在显式总和操作中聚合，非等间隔观测不作默认算术平均。

## 证据及责任
科学模型、工程 Adapter、LLM 推荐、科学校验和用户审核是独立职责。LLM 不替代专业模型机理。模型选择必须先通过硬约束；运行成功不等同于科学验证或管理审核。手算测试数值容差按具体算法设定，不能用大容差隐藏错误。后续空间覆盖、栅格转换、真实数据验证、模型校准和专业审核仍需完成。

## 实施时核对的依赖文档
- [Pydantic 模型与校验](https://docs.pydantic.dev/latest/concepts/models/)
- [Pint 单位转换](https://pint.readthedocs.io/en/stable/getting/tutorial.html)
- [PyProj 坐标转换](https://pyproj4.github.io/pyproj/stable/api/transformer.html)
- [NumPy 向量范数](https://numpy.org/doc/stable/reference/generated/numpy.linalg.norm.html)


## 文件层与确定性演示补充
GeoTIFF 仅接收 GTiff 内存字节，限制压缩字节和解码像元数；禁止 VRT/任意 URL。NoData 保留为 NaN/JSON null；单位、CRS 与垂向元数据必须与不可变目录一致。投影格网面积由仿射行列式乘坐标轴米制转换计算；投影畸变仍须在场景选择时审查，不把经纬度平方当平方米。

参考实现接口：[Rasterio 重投影](https://rasterio.readthedocs.io/en/stable/topics/reproject.html)、[Rasterio MemoryFile](https://rasterio.readthedocs.io/en/latest/api/rasterio.io.html)。类别量最近邻；总量场禁止用连续量插值替代面积守恒重分配。

`sample-data/README.md` 说明合成数据假设，manifest 保留文件校验和。三场景计算产物保存在 artifacts/research；人口按行政单元淹没面积比例估计，不能解释为真实精确人数。固定参考范围与权重跨期复用。当前仅有计算层与通用工作流执行链的分离证据，三场景界面/规划/绑定/执行 E2E 尚待完成。


## GIS 运算与进程隔离补充
RasterGISAdapter 使用真实 Rasterio/Shapely 运算。矢量输入携带明确 CRS；内部投影几何映射不冒充 WGS84 GeoJSON 导出。缓冲在经审查的投影坐标中计算，每象限 32 段逼近；叠加 union 明确 dissolve，并保留来源标识，不推断属性聚合。参考：[Shapely 操作接口](https://shapely.readthedocs.io/en/stable/_reference.html)。

栅格表达式先转换到基础单位再计算，检查推导输出量纲；加减、比较与 where 分支的数值字面量按另一操作数的基础单位解释，乘除字面量无量纲。NoData 不填零。

总量格网转换采用同一经审查投影中的真实像元多边形相交面积，STRtree 检索，逐源覆盖比例和总量均须在 1e-10 容差内守恒。未知值、未完整覆盖的源格网或部分覆盖目标格网明确拒绝，不外推人口。跨 CRS 的保守分配仍需额外审查的面积映射，尚不宣称已实现。

模型持久化签名包含估计器、特征名及顺序、训练/验证分组和随机种子；预测顺序不匹配被拒绝。子进程采集已按 [Coverage 官方进程文档](https://coverage.readthedocs.io/en/latest/subprocess.html) 验证，当前分支覆盖率仍未达到项目门槛。

## 实体对齐的评价节点

指标框架为结构化容器，每列分别声明观测单位与参考单位。标准化前用 Pint 将参考上下界转换到观测单位；范围之外不裁剪或补值。实体标识唯一且贯穿标准化、权重、评分和变化节点。固定参考区间与同一组权重跨期共享，避免用每期独立缩放制造趋势。熵权如用于多期，基于整个已声明观测立方体一次估计共同权重。

分类边界为左闭右开，等于断点进入下一类。变化为末期减首期；趋势为按明确年份坐标的最小二乘斜率，单位 1/year；并列排名保留同名次。多期 TOPSIS 在未定义共享理想点时拒绝执行。`indicator_frames.py` 的独立手算测试及 `builtin-assessment` 真实 DAG 测试记录了这些约束。组件注册时还执行小型金标准计算，ModelSpec.validation_metrics 中的误差为实际测得值，不是外部科学模型认证。

## 栅格与矢量空间支撑

执行时重新读取栅格格式、CRS、单位、范围与分辨率，目录声明不能覆盖文件事实。矢量使用 spatial_support_m，避免将管理单元大小称作像元分辨率。多边形默认支撑为面积平方根，投影坐标使用轴单位换算后的平面面积，地理坐标使用已声明椭球的测地面积；同时保留最小支撑。点/线无法用此规则得到面积支撑时需明确目录声明。该量描述空间支撑，不是测量精度。矢量转换采用 always_xy、allow_ballpark=False，并实际改变几何后更新其 CRS。
